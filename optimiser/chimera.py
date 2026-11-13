"""
chimera.py - the Chimera trial team builder: one team that clears a column of trials (Wing,
Tail or Paw: Easy, then Normal, then Hard) in all three of the Chimera's animal forms in a
single Ultra Nightmare fight, the column holding this rotation's mythical materials. Rewards
only count for trials cleared in the same fight, and each Normal or Hard trial only starts
once the one above it is done.

A team qualifies on what its skills can place and do: the buffs, debuffs and mechanics each
trial's rules check (`trial_needs`, held against the trial's own list of status effects by
`check_needs`), with the form's immunities. Damage isn't modelled: a trial's target is shown,
not checked, nor are skill chances, turn order or who holds a buff when it counts. Gear sets,
masteries and blessings don't count either (Retaliation, Stoneskin…): skills only.

- `PARTS`, `ANIMAL_FORMS`, `PLAN_DIFFICULTY`, `TEAM_SIZE`: what's planned
- `Side`, `Tag`, `Mechanic`: what a champion can bring
- `AnyOf`, `Distinct`, `Need`: what a trial needs
- `Kit`, `NeedCover`, `TrialCover`, `Team`, `Plan`: a champion's tags, and the result
- `plan_teams`: the workflow
- `column_trials`, `trial_needs`, `check_needs`, `candidates`, `kit_of`, `search`,
  `cover`, `core_of`: its steps
- `debuff`, `buff`, `status_kind`, `rule_count`, `tag_label`: what they share
"""

import re
from dataclasses import dataclass
from enum import StrEnum

import highspy

from optimiser.account import Account, Champion
from optimiser.enemies import Enemies, Trial

PARTS = ("Wing", "Tail", "Paw")  # the trial columns
ANIMAL_FORMS = ("Ram", "Lion", "Snake")  # the trial rows
LEVELS = ("Easy", "Normal", "Hard")
PLAN_DIFFICULTY = "UltraNightmare"
TEAM_SIZE = 5

# What every form of the Chimera is immune to (its Almighty passives: control debuffs), and
# what each form lets through all the same (Almighty Ram, Almighty Viper).
BOSS_IMMUNE = frozenset(
    {
        "Petrification",
        "Stun",
        "Freeze",
        "Sleep",
        "Provoke",
        "BlockActiveSkills",
        "BlockPassiveSkills",
        "Fear",
        "Enfeeble",
        "Ensnare",
        "Fatigue",
        "HuntersMark",
    }
)
FORM_ALLOWS = {"Ram": frozenset({"Fear"}), "Snake": frozenset({"BlockActiveSkills"})}

# Status effects whose instances stack (Poisons), so several count toward a debuff count.
STACKING = frozenset({"ContinuousDamage"})

# What a status effect kind is called in game, where its name doesn't say.
STATUS_LABELS = {
    "IncreaseDamageTaken": "Weaken",
    "Invisible": "Veil / Perfect Veil",
    "LifeDrainOnDamage": "Leech",
    "IncreasePoisoning": "Poison Sensitivity",
    "ContinuousDamage": "Poison",
    "Burn": "HP Burn",
    "FireMark": "Smite",
    "MirrorDamage": "Pain Link",
    "Negator": "Intercept",
    "SimpleStoneSkin": "Stone Skin",
    "BlockDebuff": "Block Debuffs",
    "ReviveOnDeath": "Revive on Death",
    "DecreaseDefence": "Decrease DEF",
    "DecreaseAttack": "Decrease ATK",
    "DecreaseSpeed": "Decrease SPD",
    "DecreaseAccuracy": "Decrease ACC",
    "DecreaseResistance": "Decrease RES",
    "IncreaseDefence": "Increase DEF",
    "IncreaseAttack": "Increase ATK",
    "IncreaseSpeed": "Increase SPD",
    "IncreaseAccuracy": "Increase ACC",
    "IncreaseResistance": "Increase RES",
    "IncreaseCriticalChance": "Increase C.RATE",
    "IncreaseCriticalDamage": "Increase C.DMG",
}


class Side(StrEnum):
    DEBUFF = "debuff"  # on the Chimera
    BUFF = "buff"  # on the team
    MECHANIC = "mechanic"


class Mechanic(StrEnum):
    TARGET_HP_DAMAGE = "damage based on enemy MAX HP"
    COUNTER_OR_ALLY_ATTACK = "counterattack or Ally Attack skill"
    PASSIVE_REFLECT = "passive Reflect Damage"
    REVIVE = "revive"
    PASSIVE_UNKILLABLE = "passive Unkillable"


@dataclass(frozen=True)
class Tag:
    """Something a champion can bring: a status effect kind it places (`DecreaseDefence`,
    both strengths), or a mechanic (a `Mechanic` value)."""

    side: Side
    name: str


@dataclass(frozen=True)
class AnyOf:
    """At least one of these on the team."""

    tags: frozenset[Tag]


@dataclass(frozen=True)
class Distinct:
    """At least `count` different status effects of a side (debuffs the form isn't immune
    to, or buffs), `excluded` not counting; `stacking`: Poisons count once per skill that
    places them."""

    side: Side
    count: int
    stacking: bool = False
    excluded: frozenset[str] = frozenset()


type Need = AnyOf | Distinct


@dataclass(frozen=True)
class Kit:
    champion: Champion
    tags: frozenset[Tag]
    stacking_skills: int  # its skills that place Poison


@dataclass(frozen=True)
class NeedCover:
    """A need, whether the team meets it, and who in the team brings what it asks."""

    label: str
    met: bool
    by: tuple[str, ...]  # champion names


@dataclass(frozen=True)
class TrialCover:
    """A trial and whether the team clears it: its needs met, and the one above it cleared."""

    trial: Trial
    met: bool
    needs: tuple[NeedCover, ...]


@dataclass(frozen=True)
class Team:
    """A team: `core` the champions it needs (dropping one clears fewer trials), `flexible`
    the rest (any champion would do)."""

    core: tuple[Champion, ...]
    flexible: tuple[Champion, ...]
    trials: tuple[TrialCover, ...]

    @property
    def cleared(self) -> int:
        return sum(cover.met for cover in self.trials)


@dataclass(frozen=True)
class Plan:
    column: str
    trials: tuple[Trial, ...]  # the column's, form by form, Easy first
    teams: tuple[Team, ...]  # best first
    problems: tuple[str, ...]  # trials whose needs disagree with the game's data
    candidates: int  # champions considered


def plan_teams(
    account: Account, enemies: Enemies, column: str, min_grade: int = 6, teams: int = 5
) -> Plan:
    """Up to `teams` teams, best first, of champions at `min_grade`★ or above, each with a
    different core."""
    # 1. The column's nine trials, and what each needs.
    trials = column_trials(enemies, column)
    needs = {trial.skill: trial_needs(trial) for trial in trials}
    problems = tuple(
        problem for trial in trials if (problem := check_needs(trial, needs[trial.skill]))
    )

    # 2. The champions that could take part, and what each brings.
    kits = [kit_of(account, champion) for champion in candidates(account, min_grade)]

    # 3. Teams, each clearing as many trials as it can; a team's core is never repeated.
    found = search(kits, trials, needs, teams)
    return Plan(column, tuple(trials), tuple(found), problems, len(kits))


def column_trials(enemies: Enemies, column: str) -> list[Trial]:
    tier = next(t for t in enemies.chimera.tiers if t.difficulty == PLAN_DIFFICULTY)
    by_place = {(t.form, t.part, t.level): t for t in tier.trials}
    return [by_place[(form, column, level)] for form in ANIMAL_FORMS for level in LEVELS]


def trial_needs(trial: Trial) -> tuple[Need, ...]:
    """What the trial's rules ask of the team (its counts from the trial's target or rules).
    Ram Wing Hard and Snake Tail Normal ask nothing: the Chimera duels on its own, and keeping
    the team alive is down to the team."""
    match (trial.form, trial.part, trial.level):
        case ("Ram", "Wing", "Easy"):
            return (AnyOf(debuff("Fear")),)
        case ("Ram", "Wing", "Normal"):
            hp_based = debuff("ContinuousDamage", "Burn", "FireMark")
            return (AnyOf(hp_based | {Tag(Side.MECHANIC, Mechanic.TARGET_HP_DAMAGE)}),)
        case ("Ram", "Wing", "Hard") | ("Snake", "Tail", "Normal"):
            return ()
        case ("Ram", "Tail", "Easy"):
            return (AnyOf(buff("IncreaseAccuracy")), Distinct(Side.DEBUFF, int(trial.target)))
        case ("Ram", "Tail", "Normal"):
            crit = buff("IncreaseCriticalChance", "IncreaseCriticalDamage")
            return (AnyOf(debuff("IncreaseDamageTaken")), AnyOf(crit))
        case ("Ram", "Tail", "Hard"):
            return (AnyOf(debuff("IncreaseDamageTaken")), AnyOf(debuff("DecreaseDefence")))
        case ("Ram", "Paw", "Easy"):
            return (AnyOf(debuff("DecreaseDefence")), AnyOf(buff("Invisible")))
        case ("Ram", "Paw", "Normal"):
            half = int(trial.target) // 2
            return (Distinct(Side.DEBUFF, half), Distinct(Side.BUFF, half))
        case ("Ram", "Paw", "Hard"):
            return (AnyOf(buff("BlockDebuff", "Negator", "SimpleStoneSkin")),)
        case ("Lion", "Wing", "Easy"):
            count = rule_count(trial, "DEBUFF_COUNT>=")
            return (AnyOf(buff("IncreaseDefence")), Distinct(Side.DEBUFF, count, stacking=True))
        case ("Lion", "Wing", "Normal"):
            return (AnyOf(buff("Shield")),)
        case ("Lion", "Wing", "Hard"):
            unkillable = {Tag(Side.MECHANIC, Mechanic.PASSIVE_UNKILLABLE)}
            return (AnyOf(buff("BlockDamage", "Unkillable") | unkillable),)
        case ("Lion", "Tail", "Easy"):
            return (Distinct(Side.BUFF, rule_count(trial, "RelationProducerBuffCount>=")),)
        case ("Lion", "Tail", "Normal"):
            return (AnyOf(debuff("DecreaseSpeed")), AnyOf(debuff("DecreaseDefence")))
        case ("Lion", "Tail", "Hard"):
            counter = {Tag(Side.MECHANIC, Mechanic.COUNTER_OR_ALLY_ATTACK)}
            return (AnyOf(buff("Counterattack") | counter),)
        case ("Lion", "Paw", "Easy"):
            return (AnyOf(debuff("LifeDrainOnDamage")),)
        case ("Lion", "Paw", "Normal"):
            count = int(trial.target)
            return (AnyOf(debuff("DecreaseResistance")), Distinct(Side.DEBUFF, count, True))
        case ("Lion", "Paw", "Hard"):
            passive = {Tag(Side.MECHANIC, Mechanic.PASSIVE_REFLECT)}
            return (AnyOf(buff("ReflectDamage") | debuff("MirrorDamage") | passive),)
        case ("Snake", "Wing", "Easy"):
            return (AnyOf(debuff("BlockActiveSkills")),)
        case ("Snake", "Wing", "Normal"):
            return (AnyOf(debuff("BlockBuffs")), AnyOf(debuff("Burn")))
        case ("Snake", "Wing", "Hard"):
            # It mustn't be under Block Active Skills while the debuffs count.
            count = rule_count(trial, "DEBUFF_COUNT>=")
            return (Distinct(Side.DEBUFF, count, True, frozenset({"BlockActiveSkills"})),)
        case ("Snake", "Tail", "Easy"):
            return (AnyOf(debuff("ContinuousDamage")), AnyOf(debuff("IncreasePoisoning")))
        case ("Snake", "Tail", "Hard"):
            revive = frozenset({Tag(Side.MECHANIC, Mechanic.REVIVE)})
            return (AnyOf(revive | buff("ReviveOnDeath")),)
        case ("Snake", "Paw", "Easy"):
            return (AnyOf(debuff("DecreaseAttack")), AnyOf(buff("IncreaseSpeed")))
        case ("Snake", "Paw", "Normal"):
            return (AnyOf(buff("BlockDebuff")), AnyOf(buff("IncreaseAttack")))
        case ("Snake", "Paw", "Hard"):
            return (AnyOf(debuff("DecreaseAccuracy")), AnyOf(buff("IncreaseResistance")))

    raise ValueError(f"unknown trial {trial.form} {trial.part} {trial.level}")


def check_needs(trial: Trial, needs: tuple[Need, ...]) -> str | None:
    """Why the needs don't fit the trial, if they don't: each status effect the game lists for
    the trial must be one the needs ask for (DuelTargetMark is the Chimera's own), and none
    may be one the form is immune to."""
    asked = {tag.name for need in needs if isinstance(need, AnyOf) for tag in need.tags} | {
        "DuelTargetMark"
    }
    missing = sorted({status_kind(s) for s in trial.statuses} - asked)
    if missing:
        return f"{trial.form} {trial.part} {trial.level}: the game also lists {', '.join(missing)}"

    immune = sorted(
        tag.name
        for need in needs
        if isinstance(need, AnyOf)
        for tag in need.tags
        if tag.side == Side.DEBUFF and tag.name in immune_to(trial.form)
    )
    if immune:
        return f"{trial.form} {trial.part} {trial.level}: asks for {', '.join(immune)}, immune"

    return None


def candidates(account: Account, min_grade: int) -> list[Champion]:
    """Champions at `min_grade`★ or above, the best copy of each (ascensions together)."""
    best: dict[int, Champion] = {}

    for champion in account.champions.values():
        if champion.grade < min_grade:
            continue

        kind = champion.type_id // 10
        held = best.get(kind)
        if held is None or strength(champion) > strength(held):
            best[kind] = champion

    return sorted(best.values(), key=lambda c: c.name)


def kit_of(account: Account, champion: Champion) -> Kit:
    """What the champion's skills can bring, in any of its forms (mythicals have two)."""
    skills = [
        account.tables.skills[skill_id]
        for form in account.tables.hero_forms.get(champion.type_id, ())
        for skill_id in form.skills
        if skill_id in account.tables.skills
    ]
    tags: set[Tag] = set()
    stacking = 0

    for skill in skills:
        tags |= debuff(*map(status_kind, skill.debuffs)) | buff(*map(status_kind, skill.buffs))
        tags |= {Tag(Side.MECHANIC, m) for m in skill_mechanics(skill)}
        stacking += any(status_kind(s) in STACKING for s in skill.debuffs)

    return Kit(champion, frozenset(tags), stacking)


def skill_mechanics(skill) -> set[Mechanic]:
    kinds = skill.effect_kinds
    found = set()

    if skill.target_hp_damage:
        found.add(Mechanic.TARGET_HP_DAMAGE)

    counters = {"TeamAttack", "PassiveCounterattack", "ActivateCounterattack"}
    if kinds & counters:
        found.add(Mechanic.COUNTER_OR_ALLY_ATTACK)

    if "PassiveReflectDamage" in kinds:
        found.add(Mechanic.PASSIVE_REFLECT)

    if "Revive" in kinds:
        found.add(Mechanic.REVIVE)

    if "PassiveUnkillable" in kinds:
        found.add(Mechanic.PASSIVE_UNKILLABLE)

    return found


def search(
    kits: list[Kit], trials: list[Trial], needs: dict[int, tuple[Need, ...]], teams: int
) -> list[Team]:
    """Teams clearing the most trials (then of the strongest champions), each time barring
    the cores found so far."""
    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    picked = [highs.addBinary() for _ in kits]
    cleared = {trial.skill: highs.addBinary() for trial in trials}
    highs.addConstr(highs.qsum(picked) <= TEAM_SIZE)

    for trial in trials:
        if trial.requires in cleared:
            highs.addConstr(cleared[trial.skill] <= cleared[trial.requires])

        for need in needs[trial.skill]:
            add_need(highs, need, trial.form, kits, picked, cleared[trial.skill])

    # A trial outweighs any team's strength (`strength` is under 1 per champion).
    objective = 10 * TEAM_SIZE * highs.qsum(cleared.values()) + highs.qsum(
        strength(kit.champion) * x for kit, x in zip(kits, picked, strict=True)
    )
    found: list[Team] = []

    while len(found) < teams:
        highs.maximize(objective)

        if highs.getModelStatus() != highspy.HighsModelStatus.kOptimal:
            break

        chosen = [kit for kit, x in zip(kits, picked, strict=True) if highs.val(x) > 0.5]
        team = cover(chosen, trials, needs)
        if found and team.cleared == 0:
            break

        found.append(team)
        core_vars = [picked[kits.index(k)] for k in chosen if k.champion in team.core]
        if not core_vars:
            break

        highs.addConstr(highs.qsum(core_vars) <= len(core_vars) - 1)

    return found


def add_need(highs: highspy.Highs, need: Need, form: str, kits: list[Kit], picked, on) -> None:
    """Holds the need whenever `on` (the trial cleared) is 1."""
    match need:
        case AnyOf(tags=tags):
            bringing = [x for kit, x in zip(kits, picked, strict=True) if kit.tags & tags]
            highs.addConstr(highs.qsum(bringing) >= on)

        case Distinct(side=side, count=count, stacking=stacking):
            pool = sorted(
                {tag.name for kit in kits for tag in kit.tags if counts_toward(tag, need, form)}
            )
            present = []

            for name in pool:
                tag = Tag(side, name)
                placed = highs.addBinary()
                bringing = [x for kit, x in zip(kits, picked, strict=True) if tag in kit.tags]
                highs.addConstr(placed <= highs.qsum(bringing))
                present.append(placed)

            extra = []

            if stacking:
                extra = [kit.stacking_skills * x for kit, x in zip(kits, picked, strict=True)]

            highs.addConstr(highs.qsum(present) + highs.qsum(extra) >= count * on)


def counts_toward(tag: Tag, need: Distinct, form: str) -> bool:
    """Whether the tag is one of the distinct effects the need counts; a Poison counts as its
    skills when they stack (`Kit.stacking_skills`) instead of once."""
    if tag.side != need.side:
        return False

    if need.stacking and tag.name in STACKING or tag.name in need.excluded:
        return False

    return tag.side != Side.DEBUFF or tag.name not in immune_to(form)


def cover(kits: list[Kit], trials: list[Trial], needs: dict[int, tuple[Need, ...]]) -> Team:
    """The trials the team clears, who brings each need, and its core."""
    covers = trial_covers(kits, trials, needs)
    core = core_of(kits, trials, needs, sum(c.met for c in covers))
    flexible = [kit.champion for kit in kits if kit not in core]
    return Team(
        core=tuple(sorted((k.champion for k in core), key=lambda c: c.name)),
        flexible=tuple(sorted(flexible, key=lambda c: c.name)),
        trials=covers,
    )


def trial_covers(
    kits: list[Kit], trials: list[Trial], needs: dict[int, tuple[Need, ...]]
) -> tuple[TrialCover, ...]:
    met: dict[int, bool] = {}
    covers = []

    for trial in trials:
        need_covers = tuple(need_cover(need, trial.form, kits) for need in needs[trial.skill])
        above = met.get(trial.requires, True) if trial.requires else True
        met[trial.skill] = above and all(n.met for n in need_covers)
        covers.append(TrialCover(trial, met[trial.skill], need_covers))

    return tuple(covers)


def need_cover(need: Need, form: str, kits: list[Kit]) -> NeedCover:
    match need:
        case AnyOf(tags=tags):
            by = tuple(kit.champion.name for kit in kits if kit.tags & tags)
            label = " or ".join(sorted(tag_label(tag) for tag in tags))
            return NeedCover(label, bool(by), by)

        case Distinct(side=side, count=count, stacking=stacking):
            names = {tag.name for kit in kits for tag in kit.tags if counts_toward(tag, need, form)}
            stacks = sum(kit.stacking_skills for kit in kits) if stacking else 0
            by = tuple(sorted(STATUS_LABELS.get(n, spaced(n)) for n in names))
            where = "on the Chimera" if side == Side.DEBUFF else "on the team"
            poison = f" (Poisons count per skill: {stacks})" if stacking else ""
            label = f"{count} different {side}s {where}{poison}"
            return NeedCover(label, len(names) + stacks >= count, by)


def core_of(
    kits: list[Kit], trials: list[Trial], needs: dict[int, tuple[Need, ...]], cleared: int
) -> list[Kit]:
    """The champions the team can't do without: dropping each in turn (and keeping it out if
    the team still clears as many), those it can't drop."""
    core = list(kits)

    for kit in list(kits):
        without = [k for k in core if k is not kit]
        if sum(c.met for c in trial_covers(without, trials, needs)) >= cleared:
            core = without

    return core


def strength(champion: Champion) -> float:
    """Under 1: rank first, then awakening, then level."""
    return (champion.grade * 1000 + champion.awakening * 100 + champion.level) / 7000


def immune_to(form: str) -> frozenset[str]:
    return BOSS_IMMUNE - FORM_ALLOWS.get(form, frozenset())


def debuff(*kinds: str) -> frozenset[Tag]:
    return frozenset(Tag(Side.DEBUFF, kind) for kind in kinds)


def buff(*kinds: str) -> frozenset[Tag]:
    return frozenset(Tag(Side.BUFF, kind) for kind in kinds)


def status_kind(status: str) -> str:
    """A status effect's kind: its name without the strength (DecreaseDefence60, Fear2)."""
    return re.sub(r"\d+p?$", "", status)


def rule_count(trial: Trial, term: str) -> int:
    for rule in trial.rules:
        if match := re.search(re.escape(term) + r"(\d+)", rule):
            return int(match.group(1))

    raise ValueError(f"{trial.form} {trial.part} {trial.level}: no {term} in its rules")


def tag_label(tag: Tag) -> str:
    if tag.side == Side.MECHANIC:
        return tag.name

    where = "on the Chimera" if tag.side == Side.DEBUFF else "on the team"
    return f"{STATUS_LABELS.get(tag.name, spaced(tag.name))} {where}"


def spaced(name: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
