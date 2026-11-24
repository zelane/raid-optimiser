"""
The models of the game's formulas against the game's own code: the hit (optimiser/hit.py) and
the resist roll (optimiser/accuracy.py). Each case is built twice, as the model's inputs and as
the game's objects, and the game's methods run in an emulator (tools/game_emulator.py). Results
must match bit for bit. Skipped unless `just test-game` says where the game's files are.
"""

import random
import struct

import pytest

from optimiser import accuracy, fixed, hit
from optimiser.fixed import ONE
from optimiser.hit import Affinity, Chances, DamageStats, Fighter, Hit, HitType, Status

GAME = None
try:
    from tools.game_emulator import Emulator, Game, Nullable, to_signed

    GAME = Game.from_environment()
except ImportError:  # the emulate group isn't installed
    pass

pytestmark = pytest.mark.skipif(GAME is None, reason="needs the game's files: just test-game")

CASES = 1000
CALCULATOR = "SharedModel.Battle.Core.DamageCalculator$$"
FIXED = "Plarium.Common.Numerics.Fixed$$"
ACTION_RESULTS = {18: "DamageResult", 19: "DamageResult"}  # ActionResultType ids Calculate takes
TARGET_TYPES = "SharedModel.Battle.Effects.EffectTargetTypeExtensions"
TARGETS: dict[str, int] = {}  # the EffectTargetTypes a test hit uses, from the dump
DAMAGE_CONTEXT = "SharedModel.Battle.Core.Skill.EffectContexts.DamageContext$$"


@pytest.fixture(scope="module")
def game() -> Emulator:
    emulator = Emulator(GAME)
    install_static_data(emulator)
    emulator.replace(
        "SharedModel.Battle.Core.Pool.BattlePools$$TakeResultType<object>", take_result
    )
    # which statuses influenced the hit, in a HashSet (generic code): bookkeeping, not damage
    emulator.replace(DAMAGE_CONTEXT + "AddInfluencedEffect", lambda e, arguments: 0)
    target_types = emulator.type("SharedModel.Battle.Effects.EffectTargetType").consts
    TARGETS.update(single=target_types["Target"], aoe=target_types["AllEnemies"])
    aoe_targets = emulator.static_array(TARGET_TYPES, "AoeTargets")
    assert TARGETS["aoe"] in aoe_targets and TARGETS["single"] not in aoe_targets
    return emulator


def install_static_data(e: Emulator) -> None:
    gameplay = static_gameplay()
    static = e.new(
        "SharedModel.Meta.StaticData",
        GameplayData=e.new("StaticGameplayData", **gameplay),
        StageData=e.new("StaticStageData"),
        HeroData=e.new("StaticHeroData"),
    )
    parameters = e.new("GameParameters", BattleSettings=e.new("BattleSettings"))
    e.set_static("SharedModel.SharedModelManager", StaticData=static, GameParameters=parameters)


def static_gameplay() -> dict[str, int]:
    """The model's constants as GameplayData's fields."""
    constants = hit.GAMEPLAY
    return {
        "ElementDisadvantageCoef": constants.element_disadvantage,
        "CrushingHitCoef": constants.crushing_hit,
        "GlancingHitCoef": constants.glancing_hit,
        "CriticalHitChanceAdvantage": constants.critical_chance_advantage,
        "CrushingHitChance": constants.crushing_chance,
        "GlancingHitChance": constants.glancing_chance,
    }


def take_result(e: Emulator, arguments: list[int]) -> int:
    """`BattlePools.TakeResultType<T>(pool, type)`: a fresh result object, not a pooled one."""
    return e.new(ACTION_RESULTS[arguments[1] & 0xFFFFFFFF])


# --- the game's objects for the model's inputs ------------------------------------------------


def battle_hero(e: Emulator, fighter: Fighter, owner: int) -> int:
    stats = e.new(
        "BattleStats",
        CriticalChance=fighter.critical_chance,
        CriticalDamage=fighter.critical_damage,
        Defence=fighter.defence,
        IgnoreDefence=fighter.ignore_defence,
    )
    boss_data = e.new("SharedModel.Meta.Heroes.BossData") if fighter.boss else 0
    s, d = fighter.status, fighter.damage_stats
    state = e.new(
        "HeroState",
        IsFrozen=s.frozen,
        IsWeakInvisible=s.veil,
        IsStrongInvisible=s.perfect_veil,
        IsUnderPoisonCloud=s.poison_cloud,
        IsBurning=s.burning,
        IsEnfeeble=s.enfeebled,
    )
    damage_stats = e.new(
        "ConditionalDamageStats",
        DealtDamagePve=d.dealt_pve,
        DealtDamagePvp=d.dealt_pvp,
        DealtDamageBoss=d.dealt_boss,
        DealtDamageDungeons=d.dealt_dungeons,
        TakenDamagePve=d.taken_pve,
        TakenDamagePvp=d.taken_pvp,
        TakenDamageBoss=d.taken_boss,
        TakenDamageDungeons=d.taken_dungeons,
    )
    return e.new(
        "BattleHero",
        Stats=stats,
        _type=e.new("SharedModel.Meta.Heroes.HeroType", BossData=boss_data),
        _heroState=state,
        DamageStats=damage_stats,
        OwnerUserId=owner,
    )


def battle_context(e: Emulator, area: int, random_state: hit.Random, ignore_random=False) -> int:
    stage = e.new(
        "SharedModel.Meta.Stages.Stage", _area=e.new("SharedModel.Meta.Stages.Area", Id=area)
    )
    x, y, z, w = random_state.words
    state = e.new(
        "BattleState",
        Random=e.new("FixedRandom", _x=x, _y=y, _z=z, _w=w),
        IgnoreRandomDamage=ignore_random,
        Pool=e.new("BattlePools"),  # its TakeResultType is answered by take_result
    )
    return e.new("BattleContext", Setup=e.new("BattleSetup", _stage=stage), State=state)


ANY_RANDOM = hit.Random((1, 2, 3, 4))


def effect_context(e: Emulator, h: Hit, random_state: hit.Random = ANY_RANDOM) -> int:
    attacker = battle_hero(e, h.attacker, owner=1)
    target = attacker if h.on_self else battle_hero(e, h.target, owner=2)
    effect = e.new(
        "SharedModel.Battle.Effects.EffectType",
        KindId=h.kind,
        TargetParams=e.new("TargetParams", TargetType=TARGETS["aoe" if h.aoe else "single"]),
        DamageParams=e.new("DamageParams", IsFixed=h.fixed_damage),
    )
    counterattack = None if h.counterattack_modifier is None else Nullable(h.counterattack_modifier)
    damage_context = e.new(
        "DamageContext",
        HitType=Nullable(int(h.hit_type)),
        ElementRelation=Nullable(int(h.affinity)),
        CriticalDamageModifier=h.critical_damage_modifier,
        CounterattackModifier=counterattack,
        _defenceModifier=h.defence_modifier,
        _multiplierValue=h.multiplier,
    )
    return e.new(
        "SharedModel.Battle.Core.Skill.EffectContexts.EffectContext",
        Effect=effect,
        Producer=attacker,
        Target=target,
        Skill=e.new("BattleSkill", DamageModifier=h.skill_bonus),
        DamageContext=damage_context,
        BattleContext=battle_context(e, h.area, random_state),
    )


def random_state_of(e: Emulator, context: int) -> hit.Random:
    generator = e.read(context, "BattleContext", "State", "Random")
    words = struct.unpack("<4I", e.uc.mem_read(generator + 0x10, 16))
    return hit.Random(words)


# --- random inputs ----------------------------------------------------------------------------


def some_fixed(rng: random.Random, low: float, high: float) -> int:
    return rng.randint(fixed.of(low), fixed.of(high))


def some_fighter(rng: random.Random) -> Fighter:
    return Fighter(
        critical_chance=some_fixed(rng, -0.2, 1.2),
        critical_damage=some_fixed(rng, 0.5, 4),
        defence=some_fixed(rng, 0, 12000),
        ignore_defence=some_fixed(rng, 0, 0.5),
        boss=rng.random() < 0.3,
        damage_stats=DamageStats(*(some_fixed(rng, -0.3, 0.3) for _ in range(8))),
        status=Status(*(rng.random() < 0.3 for _ in range(6))),
    )


def some_hit(rng: random.Random) -> Hit:
    attacker, on_self = some_fighter(rng), rng.random() < 0.1
    return Hit(
        multiplier=some_fixed(rng, 0, 200000),
        attacker=attacker,
        target=attacker if on_self else some_fighter(rng),
        kind=rng.choice([hit.DAMAGE, hit.DAMAGE, 4017, 2007]),  # and reflected, shared
        on_self=on_self,
        skill_bonus=some_fixed(rng, 0, 0.5),
        hit_type=rng.choice(list(HitType)),
        affinity=rng.choice(list(Affinity)),
        critical_damage_modifier=some_fixed(rng, -0.2, 0.6),
        counterattack_modifier=rng.choice([None, fixed.of(-0.25), some_fixed(rng, -1, 0)]),
        defence_modifier=some_fixed(rng, -1, 0),
        area=rng.choice([1, 2, 3, 4, 6, 8, 9, 11]),
        aoe=rng.random() < 0.5,
        fixed_damage=rng.random() < 0.3,
    )


def some_random(rng: random.Random) -> hit.Random:
    return hit.Random(tuple(rng.getrandbits(32) for _ in range(4)))


# --- the tests --------------------------------------------------------------------------------


def test_fixed_arithmetic(game):
    rng = random.Random(1)
    for _ in range(CASES):
        x, y = rng.randint(-(1 << 50), 1 << 50), rng.randint(-(1 << 50), 1 << 50) or 1
        assert to_signed(game.call(FIXED + "op_Multiply", x, y)) == fixed.mul(x, y)
        assert to_signed(game.call(FIXED + "op_Division", x, y)) == fixed.div(x, y)
        assert to_signed(game.call(FIXED + "op_Addition", x, y)) == fixed.add(x, y)
        assert to_signed(game.call(FIXED + "op_Subtraction", x, y)) == fixed.sub(x, y)

        exponent = some_fixed(rng, -20, 5)
        assert to_signed(
            game.call("SharedModel.Common.Math.FixedMath$$Exp", exponent)
        ) == fixed.exp(exponent)


def test_saturation(game):
    big = fixed.MAX - 5
    assert to_signed(game.call(FIXED + "op_Addition", big, big)) == fixed.add(big, big) == fixed.MAX
    assert to_signed(game.call(FIXED + "op_Multiply", big, -big)) == fixed.mul(big, -big)


def test_random(game):
    rng = random.Random(2)
    for _ in range(CASES):
        state = some_random(rng)
        x, y, z, w = state.words
        generator = game.new("FixedRandom", _x=x, _y=y, _z=z, _w=w)
        method = "SharedModel.Common.Math.FixedRandom$$"
        assert (
            game.call(game.methods[method + "Next"][0], generator) & 0xFFFFFFFF == state.next()[0]
        )
        assert (
            to_signed(game.call(method + "NextFixed", generator)) == state.next()[1].next_fixed()[0]
        )


def test_defence_multiplier(game):
    rng = random.Random(3)
    context = game.new("SharedModel.Battle.Core.Skill.EffectContexts.EffectContext")
    for _ in range(CASES):
        defence, modifier = some_fixed(rng, 0, 15000), some_fixed(rng, -1, 0)
        target = battle_hero(game, Fighter(defence=defence), owner=2)
        expected = hit.defence_multiplier(defence, modifier)
        assert (
            to_signed(game.call(CALCULATOR + "DamageReductionByDefence", context, target, modifier))
            == expected
        )


def test_bonus_damage(game):
    rng = random.Random(4)
    for _ in range(CASES):
        h = some_hit(rng)
        context = effect_context(game, h)
        actual = to_signed(game.call(CALCULATOR + "CalculateDamage", context, h.multiplier))
        assert actual == hit.bonus_damage(h), h


def test_status_reduction(game):
    rng = random.Random(5)
    for _ in range(CASES):
        h = some_hit(rng)
        context = effect_context(game, h)
        damage_context = game.read(context, "DamageContext")
        target = game.read(context, "Target")
        actual = game.call(
            CALCULATOR + "DamageReductionByStatusEffects",
            damage_context,
            target,
            int(h.aoe),
            h.kind,
            0,
            0,
        )
        assert to_signed(actual) == hit.status_reduction(h), h


def test_calculated_and_reflected_damage(game):
    rng = random.Random(6)
    for _ in range(CASES):
        h, state = some_hit(rng), some_random(rng)
        for use_defence, model in ((1, hit.calculated_damage), (0, hit.reflected_damage)):
            context = effect_context(game, h, state)
            result = game.call(CALCULATOR + "Calculate", context, use_defence)
            damage = to_signed(game.read(result, "_value"))
            expected, state_after = model(h, state)
            assert (damage, random_state_of(game, context)) == (expected, state_after), h


def test_hit_type(game):
    rng = random.Random(7)
    for _ in range(CASES):
        h, state = some_hit(rng), some_random(rng)
        chances = Chances(
            glancing=rng.choice([None, 0, some_fixed(rng, 0, 0.5)]),
            critical=rng.choice([None, some_fixed(rng, -0.1, 1.2)]),
            crushing=rng.choice([None, 0, some_fixed(rng, 0, 0.6)]),
        )
        context = effect_context(game, h, state)
        game.set(
            game.read(context, "DamageContext"),
            HitType=None,
            GlancingHitChance=nullable(chances.glancing),
            CriticalHitChance=nullable(chances.critical),
            CrushingHitChance=nullable(chances.crushing),
        )
        clear_nullables(game, game.read(context, "DamageContext"), chances)
        reason = game.alloc(16)
        landed = game.call(CALCULATOR + "CalculateHitType", context, int(h.affinity), reason)
        expected, state_after = hit.hit_type(
            h.attacker, h.target, h.affinity, chances, state, from_other_side=not h.on_self
        )
        actual = (HitType(landed & 0xFFFFFFFF), random_state_of(game, context))
        assert actual == (expected, state_after), (h, chances)


def nullable(value: int | None):
    return None if value is None else Nullable(value)


def clear_nullables(e: Emulator, damage_context: int, chances: Chances) -> None:
    """`new` leaves a None field as it was: zero its flag."""
    for name, value in (
        ("HitType", None),
        ("GlancingHitChance", chances.glancing),
        ("CriticalHitChance", chances.critical),
        ("CrushingHitChance", chances.crushing),
    ):
        if value is None:
            e.uc.mem_write(damage_context + e.field_of(damage_context, name).offset, b"\0")


def test_damage_context(game):
    """`DamageContext..ctor`: the DEF modifier and crit chance a hit starts from."""
    rng = random.Random(8)
    for _ in range(CASES):
        h = some_hit(rng)
        skill_modifier, extra = some_fixed(rng, -1.2, 0.2), rng.choice(
            [None, some_fixed(rng, 0, 0.3)]
        )
        context = effect_context(game, h)
        params = game.read(context, "Effect", "DamageParams")
        game.set(params, DefenceModifier=skill_modifier, IncreaseCriticalHitChance=nullable(extra))
        created = game.new("DamageContext")
        game.call(DAMAGE_CONTEXT + ".ctor", created, context, h.multiplier)

        enemy_damage = h.kind == hit.DAMAGE and not h.on_self
        assert to_signed(game.read(created, "_defenceModifier")) == hit.defence_modifier(
            skill_modifier, h.attacker, enemy_damage
        ), h
        crit = to_signed(
            game.read_u64(created + game.field_of(created, "CriticalHitChance").offset + 8)
        )
        assert crit == hit.critical_chance(h.attacker, extra), h
        assert to_signed(game.read(created, "_multiplierValue")) == max(0, h.multiplier)


def test_multiplier_and_modifier_setters(game):
    rng = random.Random(9)
    damage_context = game.new("DamageContext")
    for _ in range(CASES):
        multiplier, change = some_fixed(rng, 0, 1e5), some_fixed(rng, -2e5, 1e5)
        game.call(
            SET_MULTIPLIER,
            damage_context,
            fixed.add(multiplier, change),
        )
        assert to_signed(game.read(damage_context, "_multiplierValue")) == hit.changed_multiplier(
            multiplier, change
        )

        modifier, delta = some_fixed(rng, -1, 0), some_fixed(rng, -1.5, 1.5)
        game.call(
            DAMAGE_CONTEXT + "set_DefenceModifier",
            damage_context,
            fixed.add(modifier, delta),
        )
        assert to_signed(
            game.read(damage_context, "_defenceModifier")
        ) == hit.changed_defence_modifier(modifier, delta)


# --- the hooked effects' processors -----------------------------------------------------------

PROCESSORS = "SharedModel.Battle.Core.Skill.EffectProcessing.Processors."
VARIABLES = "SharedModel.Battle.ExpressionVariables.RelatedEffectResultParamsBuilder$$"
DMG_MUL = VARIABLES + "RelatedEffectsDamageMultiplier"
CALCULATED_DMG = VARIABLES + "GetRelatedEffectCalculatedDamage"
SET_MULTIPLIER = DAMAGE_CONTEXT + "set_MultiplierValuePositive"


def formula(e: Emulator, k: int, variable: str | None = None) -> int:
    """An effect's compiled formula (`Func<EffectContext, Fixed>`): k, or k × a variable read by
    the game's own getter (`k*DMG_MUL`), as x86 the delegate calls."""
    if variable is None:
        code = b"\x48\xb8" + struct.pack("<q", k) + b"\xc3"  # mov rax, k; ret
    else:
        getter = e.base + e.methods[variable][0]
        multiply = e.base + e.methods[FIXED + "op_Multiply"][0]
        code = b"".join(
            [
                b"\x48\x83\xec\x28",  # sub rsp, 0x28
                b"\x48\x89\xd1\x31\xd2",  # mov rcx, rdx (the context); xor edx, edx
                b"\x48\xb8" + struct.pack("<Q", getter) + b"\xff\xd0",  # call the getter
                b"\x48\x89\xc1",  # mov rcx, rax
                b"\x48\xba" + struct.pack("<q", k) + b"\x45\x31\xc0",  # mov rdx, k; xor r8d
                b"\x48\xb8" + struct.pack("<Q", multiply) + b"\xff\xd0",  # call op_Multiply
                b"\x48\x83\xc4\x28\xc3",  # add rsp, 0x28; ret
            ]
        )
    stub = e.alloc(len(code))
    e.uc.mem_write(stub, code)
    delegate = e.new("System.Func<EffectContext, Fixed>")
    e.write_u64(delegate + 0x18, stub)  # Delegate.method_ptr
    return delegate


def run_processor(e: Emulator, processor: str, related: int, kind: int, delegate: int, setter: str):
    """One hooked effect on the related hit, up to the setter that changes it (what follows is
    the action results' bookkeeping)."""
    effect = e.new("SharedModel.Battle.Effects.EffectType", KindId=kind, CalcMultiplier=delegate)
    context = e.new(
        "SharedModel.Battle.Core.Skill.EffectContexts.EffectContext",
        Effect=effect,
        RelatedContext=related,
        BattleContext=e.read(related, "BattleContext"),
        Producer=e.read(related, "Producer"),
        Target=e.read(related, "Target"),
    )
    method = PROCESSORS + processor + "$$Process"
    e.call(method, e.new(processor), context, until=e.after_call(method, setter))


def some_changes(rng: random.Random) -> list[tuple[int, bool]]:
    """1-4 formulas: (k, whether it's k × the variable rather than k)."""
    return [(some_fixed(rng, -0.6, 0.6), rng.random() < 0.7) for _ in range(rng.randint(1, 4))]


def test_damage_multiplier_changes(game):
    """`ChangeDamageMultiplier`s (sets, masteries, passives): each adds its formula, read with
    DMG_MUL as it stands then, so `k*DMG_MUL` bonuses compound; a blocked hit keeps its own."""
    rng = random.Random(10)
    for _ in range(CASES // 3):
        h, changes, blocked = some_hit(rng), some_changes(rng), rng.random() < 0.15
        related = effect_context(game, h)
        damage_context = game.read(related, "DamageContext")
        game.set(damage_context, IsBlocked=blocked)

        expected = h.multiplier
        for k, of_multiplier in changes:
            delegate = formula(game, k, DMG_MUL if of_multiplier else None)
            run_processor(
                game, "ChangeDamageMultiplierProcessor", related, 7004, delegate, SET_MULTIPLIER
            )
            if not blocked:
                change = fixed.mul(k, expected) if of_multiplier else k
                expected = hit.changed_multiplier(expected, change)

        assert to_signed(game.read(damage_context, "_multiplierValue")) == expected, (h, changes)


def test_zeal_and_fury_compound(game):
    """Zeal 3 (+36 %) and Fury at full HP (+10 %) on a 1000 multiplier: 1496, not 1460."""
    related = effect_context(
        game, Hit(multiplier=fixed.of(1000), attacker=Fighter(), target=Fighter())
    )
    for bonus in (0.36, 0.10):
        delegate = formula(game, fixed.of(bonus), DMG_MUL)
        run_processor(
            game,
            "ChangeDamageMultiplierProcessor",
            related,
            7004,
            delegate,
            SET_MULTIPLIER,
        )
    result = fixed.to_float(to_signed(game.read(related, "DamageContext", "_multiplierValue")))
    assert round(result, 6) == 1496


def test_status_multipliers(game):
    """Weaken, Strengthen, Rage, Inspiration: the multiplier times the formula."""
    rng = random.Random(11)
    for _ in range(CASES // 3):
        h = some_hit(rng)
        factors = [
            rng.choice(
                [
                    fixed.of(1.25),
                    fixed.of(1.15),
                    fixed.of(0.85),
                    fixed.of(0.75),
                    some_fixed(rng, 0, 2),
                ]
            )
            for _ in range(rng.randint(1, 3))
        ]
        related = effect_context(game, h)
        expected = h.multiplier
        for factor in factors:
            run_processor(
                game,
                "StatusChangeDamageMultiplierProcessor",
                related,
                3010,
                formula(game, factor),
                SET_MULTIPLIER,
            )
            expected = hit.scaled_multiplier(expected, factor)
        assert to_signed(game.read(related, "DamageContext", "_multiplierValue")) == expected, (
            h,
            factors,
        )


def test_defence_modifier_changes(game):
    """Set and skill ignore DEF (`ChangeDefenceModifier`): added, clamped to [-1, 0]."""
    rng = random.Random(12)
    for _ in range(CASES // 3):
        h = some_hit(rng)
        changes = [some_fixed(rng, -0.6, 0.3) for _ in range(rng.randint(1, 4))]
        related = effect_context(game, h)
        expected = h.defence_modifier
        for change in changes:
            run_processor(
                game,
                "ChangeDefenceModifierProcessor",
                related,
                7001,
                formula(game, change),
                DAMAGE_CONTEXT + "set_DefenceModifier",
            )
            expected = hit.changed_defence_modifier(expected, change)
        assert to_signed(game.read(related, "DamageContext", "_defenceModifier")) == expected, (
            h,
            changes,
        )


def test_calculated_damage_changes(game):
    """`ChangeCalculatedDamage` (Owein's −25 %): the dealt damage changes, CALCULATED_DMG
    doesn't, so each formula reads what was calculated."""
    rng = random.Random(13)
    for _ in range(CASES // 3):
        h, changes = some_hit(rng), some_changes(rng)
        calculated = some_fixed(rng, 0, 1e6)
        related = effect_context(game, h)
        game.set(
            game.read(related, "DamageContext"),
            CalculatedDamage=game.new("DamageResult", _value=calculated),
            DealtDamage=game.new("DamageResult", _value=calculated),
        )
        expected = calculated
        for k, of_calculated in changes:
            delegate = formula(game, k, CALCULATED_DMG if of_calculated else None)
            run_processor(
                game,
                "ChangeCalculatedDamageProcessor",
                related,
                7006,
                delegate,
                "SharedModel.Battle.Core.Result.DamageResult$$set_ValuePositive",
            )
            change = fixed.mul(k, calculated) if of_calculated else k
            expected = hit.changed_dealt_damage(expected, change)

        assert to_signed(game.read(related, "DamageContext", "DealtDamage", "_value")) == expected
        assert (
            to_signed(game.read(related, "DamageContext", "CalculatedDamage", "_value"))
            == calculated
        )


# --- the resist roll --------------------------------------------------------------------------


def random_giving(roll: int) -> hit.Random:
    """A `FixedRandom` whose next `NextFixed()` is `roll` (even, in [0, 1)): xorshift run
    backwards, with the newest word 0."""
    wanted = roll >> 1
    mixed = wanted ^ (wanted >> 8) ^ (wanted >> 16) ^ (wanted >> 24)  # undo t ^ (t >> 8)
    oldest = (mixed ^ (mixed << 11) ^ (mixed << 22)) & 0xFFFFFFFF  # undo x ^ (x << 11)
    return hit.Random((oldest, 0, 0, 0))


def resisted(game: Emulator, attacker_accuracy: int, target_resistance: int, roll: int) -> bool:
    x, y, z, w = random_giving(roll).words
    generator = game.new("FixedRandom", _x=x, _y=y, _z=z, _w=w)
    method = "SharedModel.Battle.Core.Skill.EffectManager$$IsResisted"
    return bool(game.call(method, attacker_accuracy, target_resistance, generator) & 0xFF)


def game_threshold(game: Emulator, attacker_accuracy: int, target_resistance: int) -> int:
    """The largest roll the game still resists: binary search on `IsResisted`."""
    low, high = 0, ONE  # resisted at low (the floor is above 0), not at high
    while high - low > 2:
        middle = (low + high) // 4 * 2
        if resisted(game, attacker_accuracy, target_resistance, middle):
            low = middle
        else:
            high = middle
    return low


def test_random_giving():
    rng = random.Random(14)
    for _ in range(CASES):
        roll = rng.randrange(0, ONE, 2)
        assert random_giving(roll).next_fixed()[0] == roll


def test_resist_threshold(game):
    """`IsResisted(ACC, RES, random)`: resisted when the roll is at most the model's chance."""
    rng = random.Random(15)
    for _ in range(CASES // 5):
        acc = rng.choice([some_fixed(rng, 0, 900), fixed.of_int(rng.randint(0, 900))])
        res = rng.choice([acc + some_fixed(rng, -400, 500), fixed.of_int(rng.randint(0, 900))])
        expected = accuracy.resist_threshold(acc, res) // 2 * 2  # rolls are even raw values
        assert game_threshold(game, acc, res) == expected, (acc, res)
