"""
hit.py - a hit's damage as the game computes it: `DamageCalculator` and `DamageContext`, in the
game's `Fixed` arithmetic, bit for bit. The reference model behind docs/game-model.md's Damage
section, checked against the game's own code by tests/test_game_code.py (which runs
GameAssembly.dll's methods in an emulator). The solver doesn't use it: optimiser/damage.py is
its linear stand-in.

Covered: the hit's context (DEF modifier, crit chance), its hit type and the roll for it, the
multiplier's factors (`CalculateDamage`), the dealt/taken substats, the DEF multiplier, the
status reductions from Freeze and Veils, and the random roll. Not covered: Stone Skin,
Petrification and Newbie Defence (their factors are 1 here), ignoring Increase DEF buffs, and
what hooked effects do between the steps (docs/game-model.md lists them).

- `HitType`, `Affinity`, `Constants`, `GAMEPLAY`: the game's enums and GameplayData
- `DamageStats`, `Status`, `Fighter`, `Hit`: what a hit is computed from
- `Random`: the battle's `FixedRandom` (xorshift128)
- `calculated_damage`, `reflected_damage`: `DamageCalculator.Calculate` (the workflow)
- `hit_type`: `CalculateHitType`, with the roll it takes
- `defence_modifier`, `critical_chance`: what `DamageContext` starts from
- `bonus_damage`, `stat_modifier`, `defence_multiplier`, `status_reduction`, `roll`: its steps
- `changed_multiplier`, `scaled_multiplier`, `changed_defence_modifier`, `changed_dealt_damage`:
  what hooked effects do
"""

from dataclasses import dataclass, field
from enum import IntEnum

from optimiser import fixed
from optimiser.fixed import ONE, Fixed

DAMAGE = 6000  # EffectKindId.Damage: books and substats count only for it
DUNGEON = 2  # AreaTypeId
PVP_AREAS = frozenset({3, 6, 9, 11})  # Arena, Arena3x3, Live Arena, Siege: IsBattleWithPlayer
FREEZE, VEIL, PERFECT_VEIL = 20, 480, 481  # StatusEffectTypeIds a hit can ignore the reduction of


class HitType(IntEnum):
    NORMAL = 0
    CRUSHING = 1
    CRITICAL = 2
    GLANCING = 3


class Affinity(IntEnum):
    DISADVANTAGE = -1
    NEUTRAL = 0
    ADVANTAGE = 1


@dataclass(frozen=True)
class Constants:
    """The static data's `GameplayData` that a hit reads."""

    element_disadvantage: Fixed
    crushing_hit: Fixed
    glancing_hit: Fixed
    critical_chance_advantage: Fixed
    crushing_chance: Fixed
    glancing_chance: Fixed


GAMEPLAY = Constants(  # 11.95.0's (static data GameplayData; exact as raw values)
    element_disadvantage=-858993459,  # -0.2
    crushing_hit=1288490188,  # 0.3
    glancing_hit=-1288490188,  # -0.3
    critical_chance_advantage=644245094,  # 0.15
    crushing_chance=2147483648,  # 0.5
    glancing_chance=1503238553,  # 0.35
)


@dataclass(frozen=True)
class DamageStats:
    """`ConditionalDamageStats`: dealt and taken damage substats, by kind of battle."""

    dealt_pve: Fixed = 0
    dealt_pvp: Fixed = 0
    dealt_boss: Fixed = 0
    dealt_dungeons: Fixed = 0
    taken_pve: Fixed = 0
    taken_pvp: Fixed = 0
    taken_boss: Fixed = 0
    taken_dungeons: Fixed = 0


@dataclass(frozen=True)
class Status:
    """The `HeroState` flags a hit reads."""

    frozen: bool = False
    veil: bool = False  # IsWeakInvisible
    perfect_veil: bool = False  # IsStrongInvisible
    poison_cloud: bool = False  # IsUnderPoisonCloud: it glances hits, unless also burning
    burning: bool = False
    enfeebled: bool = False


@dataclass(frozen=True)
class Fighter:
    critical_chance: Fixed = 0
    critical_damage: Fixed = 0
    defence: Fixed = 0
    ignore_defence: Fixed = 0  # the IgnoreDefence stat
    boss: bool = False
    damage_stats: DamageStats = field(default_factory=DamageStats)
    status: Status = field(default_factory=Status)


@dataclass(frozen=True)
class Hit:
    """One damage effect's context: who hits whom, with what, and how it landed."""

    multiplier: Fixed  # the formula's value, after any hooked effects changed it
    attacker: Fighter
    target: Fighter
    kind: int = DAMAGE
    on_self: bool = False  # the producer is the target
    skill_bonus: Fixed = 0  # BattleSkill.DamageModifier: the books
    hit_type: HitType = HitType.NORMAL
    affinity: Affinity = Affinity.NEUTRAL
    critical_damage_modifier: Fixed = 0
    counterattack_modifier: Fixed | None = None
    defence_modifier: Fixed = 0  # the DamageContext's, already clamped to [-1, 0]
    area: int = 1  # AreaTypeId (Story)
    aoe: bool = False
    fixed_damage: bool = False  # DamageParams.IsFixed: no affinity, hit type or roll
    ignored_reductions: frozenset[int] = frozenset()  # StatusEffectTypeIds


@dataclass(frozen=True)
class Random:
    """`FixedRandom`: xorshift128 over four uint32 words (`_x`, `_y`, `_z`, `_w`)."""

    words: tuple[int, int, int, int]

    def next(self) -> tuple[int, "Random"]:
        """`Next()`: a value in [0, 2^31), and the state after it."""
        oldest, second, third, newest = self.words
        mixed = (oldest ^ (oldest << 11)) & 0xFFFFFFFF
        word = (newest ^ (newest >> 19) ^ mixed ^ (mixed >> 8)) & 0xFFFFFFFF
        return word & 0x7FFFFFFF, Random((second, third, newest, word))

    def next_between(self, low: int, high: int) -> tuple[int, "Random"]:
        """`Next(low, high)`: an int in [low, high)."""
        value, after = self.next()
        return low + value % (high - low), after

    def next_fixed(self) -> tuple[Fixed, "Random"]:
        """`NextFixed()`: a Fixed in [0, 1)."""
        value, after = self.next()
        return 2 * value, after


def calculated_damage(
    hit: Hit, random: Random, constants: Constants = GAMEPLAY
) -> tuple[Fixed, Random]:
    """`DamageCalculator.Calculate(cx, true)`: the hit's damage before anything absorbs it, and
    the random state after its roll."""
    against_defence = defence_multiplier(hit.target.defence, hit.defence_modifier)
    return finished_damage(hit, against_defence, random, constants)


def reflected_damage(
    hit: Hit, random: Random, constants: Constants = GAMEPLAY
) -> tuple[Fixed, Random]:
    """`Calculate(cx, false)`, as reflects call it: the target's DEF doesn't count."""
    return finished_damage(hit, ONE, random, constants)


def finished_damage(
    hit: Hit, against_defence: Fixed, random: Random, constants: Constants
) -> tuple[Fixed, Random]:
    damage = fixed.mul(bonus_damage(hit, constants), against_defence)
    damage = fixed.mul(damage, status_reduction(hit))

    if hit.fixed_damage:
        return damage, random

    factor, random = roll(random)
    return fixed.mul(damage, factor), random


@dataclass(frozen=True)
class Chances:
    """The DamageContext's hit-type chances (None: no chance at all, not even an affinity's)."""

    glancing: Fixed | None = None
    critical: Fixed | None = None
    crushing: Fixed | None = None


def hit_type(
    attacker: Fighter,
    target: Fighter,
    affinity: Affinity,
    chances: Chances,
    random: Random,
    from_other_side: bool = True,
    constants: Constants = GAMEPLAY,
) -> tuple[HitType, Random]:
    """`CalculateHitType` with no preset type and nothing ignored. A target's Poison Cloud
    glances hits from the other side (unless it's also burning), an Enfeebled attacker's hits
    glance; else one roll, checked against glancing, then crit, then crushing."""
    poison_cloud = target.status.poison_cloud and not target.status.burning
    if (poison_cloud and from_other_side) or attacker.status.enfeebled:
        return HitType.GLANCING, random

    if chances == Chances():
        return HitType.NORMAL, random

    value, random = random.next_fixed()
    weak, strong = affinity == Affinity.DISADVANTAGE, affinity == Affinity.ADVANTAGE
    if lands(chances.glancing, weak, constants.glancing_chance, value):
        return HitType.GLANCING, random

    if lands(chances.critical, strong, constants.critical_chance_advantage, value):
        return HitType.CRITICAL, random

    if lands(chances.crushing, strong, constants.crushing_chance, value):
        return HitType.CRUSHING, random

    return HitType.NORMAL, random


def lands(chance: Fixed | None, favoured: bool, bonus: Fixed, value: Fixed) -> bool:
    """`IsGlanceHit` / `IsCritHit` / `IsCrushHit`."""
    if chance is None:
        return False

    chance = fixed.add(chance, bonus) if favoured else chance
    if chance <= EPSILON:
        return False

    return chance >= ONE or value < chance


EPSILON = 0xA7C5  # Fixed.Epsilon, as the game defines it


def defence_modifier(skill_modifier: Fixed, attacker: Fighter, enemy_damage: bool) -> Fixed:
    """The `DamageContext`'s DEF modifier: the skill's, clamped to [-1, 0]; then, on a `Damage`
    hit at an enemy, less the attacker's IgnoreDefence stat, clamped again (so a skill's
    positive modifier doesn't offset the stat)."""
    modifier = fixed.clamp(skill_modifier, -ONE, 0)

    if not enemy_damage:
        return modifier

    return fixed.clamp(fixed.sub(modifier, attacker.ignore_defence), -ONE, 0)


def critical_chance(attacker: Fighter, skill_extra: Fixed | None) -> Fixed:
    """The `DamageContext`'s crit chance: C.RATE, plus the skill's `IncreaseCriticalHitChance`."""
    if skill_extra is None:
        return attacker.critical_chance

    return fixed.add(attacker.critical_chance, skill_extra)


def bonus_damage(hit: Hit, constants: Constants = GAMEPLAY) -> Fixed:
    """`DamageCalculator.CalculateDamage`: the multiplier × (1 + each bonus), in the game's
    order."""
    damage = hit.multiplier

    for bonus in (
        skill_bonus(hit),
        affinity_bonus(hit, constants),
        hit_bonus(hit, constants),
        hit.counterattack_modifier or 0,
        stat_modifier(hit),
    ):
        damage = fixed.mul(damage, fixed.add(ONE, bonus))

    return damage


def skill_bonus(hit: Hit) -> Fixed:
    return hit.skill_bonus if hit.kind == DAMAGE and not hit.on_self else 0


def affinity_bonus(hit: Hit, constants: Constants) -> Fixed:
    return constants.element_disadvantage if hit.affinity == Affinity.DISADVANTAGE else 0


def hit_bonus(hit: Hit, constants: Constants) -> Fixed:
    match hit.hit_type:
        case HitType.NORMAL:
            return 0
        case HitType.CRUSHING:
            return constants.crushing_hit
        case HitType.CRITICAL:
            return fixed.add(hit.attacker.critical_damage, hit.critical_damage_modifier)
        case HitType.GLANCING:
            return constants.glancing_hit


def stat_modifier(hit: Hit) -> Fixed:
    """`DamageModifierFromStats`: the attacker's dealt and the target's taken substats that apply
    to this battle (a `Damage` hit only)."""
    if hit.kind != DAMAGE:
        return 0

    dealt, taken = hit.attacker.damage_stats, hit.target.damage_stats

    if hit.area in PVP_AREAS:
        return fixed.add(fixed.add(0, dealt.dealt_pvp), taken.taken_pvp)

    modifier = fixed.add(fixed.add(0, dealt.dealt_pve), taken.taken_pve)

    if hit.area == DUNGEON:
        modifier = fixed.add(fixed.add(modifier, dealt.dealt_dungeons), taken.taken_dungeons)

    if hit.attacker.boss:
        modifier = fixed.add(modifier, taken.taken_boss)

    if hit.target.boss:
        modifier = fixed.add(modifier, dealt.dealt_boss)

    return modifier


def defence_multiplier(defence: Fixed, modifier: Fixed) -> Fixed:
    """`DamageReductionByDefence`: 1 − 0.85 (1 − e^(−2·effDEF / 3000)), effDEF = DEF × (1 +
    modifier)."""
    effective = fixed.mul(defence, fixed.add(ONE, modifier))
    exponent = fixed.div(fixed.mul(fixed.of_int(-2), effective), fixed.of_int(3000))
    reduction = fixed.mul(fixed.of(0.85), fixed.sub(ONE, fixed.exp(exponent)))
    return fixed.sub(ONE, reduction)


def status_reduction(hit: Hit) -> Fixed:
    """`DamageReductionByStatusEffects` from Freeze and the Veils (AoE hits only for those)."""
    status, ignored = hit.target.status, hit.ignored_reductions
    factor = ONE

    if status.frozen and FREEZE not in ignored:
        factor = fixed.sub(factor, fixed.of(0.25))

    if hit.aoe and status.veil and VEIL not in ignored:
        factor = fixed.sub(factor, fixed.of(0.075))

    if hit.aoe and status.perfect_veil and PERFECT_VEIL not in ignored:
        factor = fixed.sub(factor, fixed.of(0.15))

    return factor


def roll(random: Random) -> tuple[Fixed, Random]:
    """The random factor: n / 100 for n in [90, 110)."""
    percent, random = random.next_between(90, 110)
    return fixed.of(percent / 100), random


def changed_multiplier(multiplier: Fixed, change: Fixed) -> Fixed:
    """`ChangeDamageMultiplier`: the multiplier plus the effect's formula (never below 0)."""
    return max(0, fixed.add(multiplier, change))


def scaled_multiplier(multiplier: Fixed, factor: Fixed) -> Fixed:
    """Weaken, Strengthen, Rage, Inspiration (`StatusChangeDamageMultiplier`): times the formula."""
    return max(0, fixed.mul(multiplier, factor))


def changed_defence_modifier(modifier: Fixed, change: Fixed) -> Fixed:
    """`ChangeDefenceModifier` / `IgnoreDefenceModifier`: added, then clamped to [-1, 0]."""
    return fixed.clamp(fixed.add(modifier, change), -ONE, 0)


def changed_dealt_damage(dealt: Fixed, change: Fixed) -> Fixed:
    """`ChangeCalculatedDamage` (Owein's reduction): the dealt damage plus the formula (never
    below 0). `CALCULATED_DMG` stays what was calculated, so later formulas still read that."""
    return max(0, fixed.add(dealt, change))
