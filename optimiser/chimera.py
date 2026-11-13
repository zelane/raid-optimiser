"""
chimera.py - the Chimera trial team builder: one team that clears a column of trials (Wing,
Tail or Paw: Easy, then Normal, then Hard) in all three of the Chimera's animal forms in a
single Ultra Nightmare fight, the column holding this rotation's mythical materials. Rewards
only count for trials cleared in the same fight, and each Normal or Hard trial only starts
once the one above it is done. The user puts the champions they want in the team's slots;
the search fills the open ones.

A team qualifies on what its skills can place and do: the buffs, debuffs and mechanics each
trial's rules check (`trial_needs`, held against the trial's own list of status effects by
`check_needs`), with the form's immunities. Damage isn't modelled: a trial's target is shown,
not checked, nor are skill chances, turn order or who holds a buff when it counts. Gear counts
only as the Toxic set, which any champion can wear (Poison, when the page counts it);
other sets, masteries and blessings don't (Retaliation, Stoneskin…). The debuff-count trials
count debuffs, not kinds: Poisons stack, so a team placing them can reach the count if it's
fast enough (Snake moves the Poisons on it to the team each of its turns).

- `PARTS`, `ANIMAL_FORMS`, `PLAN_DIFFICULTY`, `TEAM_SIZE`, `SEARCH_CAP`, `SEARCH_SECONDS`,
  `PARTIAL_OPTIONS`: what's planned
- `Side`, `Tag`, `Mechanic`: what a champion can bring
- `AnyOf`, `Distinct`, `Given`, `Need`: what a trial needs
- `Gear`, `TOXIC_SET`: artifact sets any champion can wear, that meet needs for any team
- `Kit`, `NeedCover`, `TrialCover`, `Member`, `Lineup`, `Plan`: a champion's tags, and
  the result
- `check_lineup`: what the champions in the slots clear; `fill_lineup`: the workflow that
  fills the open slots, every way that clears all the trials
- `column_needs`, `column_trials`, `trial_needs`, `check_needs`, `candidates`, `kit_of`,
  `every_team` (`Check`, `check_of`, `holds`, `bringing`), `search` (when none clears every
  trial), `lineup_of`, `core_of`, `cleared_by`: their steps
- `debuff`, `buff`, `status_kind`, `rule_count`, `tag_label`, `stacking_tags`, `with_gear`:
  what they share
"""

import re
import time
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
SEARCH_CAP = 20_000  # teams found before the search stops
SEARCH_SECONDS = 1.0  # or time spent
PARTIAL_OPTIONS = 3  # teams offered when none clears every trial

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

# Status effects whose instances stack (Poisons): a team placing one can pile up a debuff
# count on its own, if it's fast enough (or extends them).
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
    """At least `count` status effects of a side (debuffs the form isn't immune to, or buffs),
    `excluded` not counting. Different ones, unless `instances`: the rule counts every debuff
    on the Chimera, so a team placing Poisons (they stack) meets it too."""

    side: Side
    count: int
    instances: bool = False
    excluded: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Given:
    """A need every team meets, thanks to `gear` (any champion can wear it)."""

    need: AnyOf | Distinct
    gear: str


type Need = AnyOf | Distinct | Given


@dataclass(frozen=True)
class Gear:
    """An artifact set any champion can wear, and what it places (the Toxic set: Poison)."""

    name: str
    tags: frozenset[Tag]


# A set any champion can wear that places what trials ask for (75% chance of a Poison a hit).
TOXIC_SET = Gear("Toxic set", frozenset({Tag(Side.DEBUFF, "ContinuousDamage")}))


@dataclass(frozen=True)
class Kit:
    champion: Champion
    tags: frozenset[Tag]


@dataclass(frozen=True)
class NeedCover:
    """A need, whether the team meets it, who in the team brings what it asks, and `notes`:
    what else does (the gear), or for a count, which effects the team brings."""

    label: str
    met: bool
    by: tuple[Champion, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrialCover:
    """A trial and whether the team clears it: its needs met, and the one above it cleared."""

    trial: Trial
    met: bool
    needs: tuple[NeedCover, ...]


@dataclass(frozen=True)
class Member:
    """A champion in a slot: `chosen` by the user (else the search's suggestion), and
    `needed`: dropping it clears fewer trials."""

    champion: Champion
    chosen: bool
    needed: bool


@dataclass(frozen=True)
class Lineup:
    """The team's slots (`TEAM_SIZE`, None when open) and the trials it clears."""

    slots: tuple[Member | None, ...]
    trials: tuple[TrialCover, ...]

    @property
    def cleared(self) -> int:
        return sum(cover.met for cover in self.trials)


@dataclass(frozen=True)
class Plan:
    """The slots as the user filled them, and (when the search ran) the teams it found
    keeping them, best first: `found` in all (`complete`: no more exist), `options` the
    first of them. `partial`: none clears every trial, so these clear the most they can."""

    column: str
    lineup: Lineup
    options: tuple[Lineup, ...]
    found: int
    complete: bool
    partial: bool
    problems: tuple[str, ...]  # trials whose needs disagree with the game's data
    candidates: int  # champions the search could add (0 when it didn't run)


def check_lineup(
    account: Account,
    enemies: Enemies,
    column: str,
    slots: tuple[Champion | None, ...],
    gear: tuple[Gear, ...],
) -> Plan:
    """What the champions in the slots clear on their own (any of them wearing `gear`)."""
    trials, needs, problems = column_needs(enemies, column, gear)
    chosen = [kit_of(account, c) if c else None for c in slots]
    lineup = lineup_of(chosen, set(), trials, needs)
    return Plan(column, lineup, (), 0, True, False, problems, 0)


def fill_lineup(
    account: Account,
    enemies: Enemies,
    column: str,
    slots: tuple[Champion | None, ...],
    min_grade: int,
    gear: tuple[Gear, ...],
    shown: int,
) -> Plan:
    """The slots' champions kept, the open slots filled with champions at `min_grade`★ or
    above (any of them wearing `gear`): every smallest team clearing all the trials (up to
    `SEARCH_CAP`, or what `SEARCH_SECONDS` finds), those needing the fewest champions first,
    then the strongest; the first `shown` of them as lineups. If none clears them all, a few
    teams clearing the most."""
    # 1. The column's nine trials, and what each needs (less what the gear brings).
    trials, needs, problems = column_needs(enemies, column, gear)

    # 2. Who's in the slots, and who could join them (the best copy of each champion).
    chosen = [kit_of(account, c) if c else None for c in slots]
    pinned = [kit for kit in chosen if kit]
    taken = {kit.champion.type_id // 10 for kit in pinned}
    others = [
        kit_of(account, champion)
        for champion in candidates(account, min_grade)
        if champion.type_id // 10 not in taken
    ]

    # 3. Every team clearing all the trials, or failing that the few clearing the most.
    found, complete = every_team(pinned, others, trials, needs, SEARCH_CAP, SEARCH_SECONDS)
    partial = not found
    if partial:
        found = search(pinned, others, trials, needs, PARTIAL_OPTIONS)
    else:
        found.sort(key=lambda added: (len(added), -sum(strength(k.champion) for k in added)))

    # 4. The first of them as lineups, each one's newcomers in the open slots in order.
    teams = []

    for added in found[:shown]:
        newcomers = iter(added)
        filled = [kit if kit else next(newcomers, None) for kit in chosen]
        teams.append(lineup_of(filled, {id(kit) for kit in added}, trials, needs))

    lineup = lineup_of(chosen, set(), trials, needs)
    return Plan(column, lineup, tuple(teams), len(found), complete, partial, problems, len(others))


def column_needs(
    enemies: Enemies, column: str, gear: tuple[Gear, ...]
) -> tuple[list[Trial], dict[int, tuple[Need, ...]], tuple[str, ...]]:
    """The column's nine trials, what each needs (`Given` where the gear meets it), and where
    the needs disagree with the game's data."""
    trials = column_trials(enemies, column)
    needs = {trial.skill: trial_needs(trial) for trial in trials}
    problems = tuple(
        problem for trial in trials if (problem := check_needs(trial, needs[trial.skill]))
    )
    return trials, {skill: with_gear(n, gear) for skill, n in needs.items()}, problems


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
            return (AnyOf(buff("IncreaseDefence")), Distinct(Side.DEBUFF, count, instances=True))
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
            return (
                AnyOf(debuff("DecreaseResistance")),
                Distinct(Side.DEBUFF, count, instances=True),
            )
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

    for skill in skills:
        tags |= debuff(*map(status_kind, skill.debuffs)) | buff(*map(status_kind, skill.buffs))
        tags |= {Tag(Side.MECHANIC, m) for m in skill_mechanics(skill)}

    return Kit(champion, frozenset(tags))


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


@dataclass(frozen=True)
class Check:
    """A need ready to test quickly: met when a team has `count` of the `counting` tags, or
    any of the `stacking` ones (for a count of debuff instances: Poisons)."""

    counting: frozenset[Tag]
    count: int
    stacking: frozenset[Tag]


def every_team(
    pinned: list[Kit],
    others: list[Kit],
    trials: list[Trial],
    needs: dict[int, tuple[Need, ...]],
    cap: int,
    seconds: float,
) -> tuple[list[list[Kit]], bool]:
    """Every smallest set of champions to add to `pinned` so the team clears all the trials
    (no one in it can be dropped), up to `cap` of them or as many as `seconds` finds, and
    whether that's all there are.
    It adds, each time, a champion bringing the unmet need fewest can bring: every such set
    is reached, once."""
    open_slots = TEAM_SIZE - len(pinned)
    checks = [
        check_of(need, trial.form, pinned + others)
        for trial in trials
        for need in needs[trial.skill]
        if not isinstance(need, Given)
    ]
    base_tags = frozenset().union(*(kit.tags for kit in pinned))
    found: list[list[Kit]] = []
    visited: set[frozenset[int]] = set()
    deadline = time.monotonic() + seconds
    stopped = False

    def clears(members: frozenset[int]) -> bool:
        tags = base_tags.union(*(others[i].tags for i in members))
        return all(holds(check, tags) for check in checks)

    def grow(members: frozenset[int], tags: frozenset[Tag]) -> None:
        nonlocal stopped

        if stopped or members in visited:
            return

        if len(found) >= cap or time.monotonic() > deadline:
            stopped = True
            return

        visited.add(members)
        unmet = [check for check in checks if not holds(check, tags)]
        if not unmet:
            if all(not clears(members - {i}) for i in members):
                found.append(sorted((others[i] for i in members), key=lambda k: k.champion.name))

            return

        if len(members) == open_slots:
            return

        choices = [bringing(check, tags, others, members) for check in unmet]
        for i in min(choices, key=len):
            grow(members | {i}, tags | others[i].tags)

    grow(frozenset(), base_tags)
    return found, not stopped


def check_of(need: AnyOf | Distinct, form: str, kits: list[Kit]) -> Check:
    match need:
        case AnyOf(tags=tags):
            return Check(tags, 1, frozenset())

        case Distinct(count=count, instances=instances):
            counting = {tag for kit in kits for tag in kit.tags if counts_toward(tag, need, form)}
            stacking = stacking_tags(need) if instances else frozenset()
            return Check(frozenset(counting), count, stacking)


def holds(check: Check, tags: frozenset[Tag]) -> bool:
    return bool(tags & check.stacking) or len(tags & check.counting) >= check.count


def bringing(check: Check, tags: frozenset[Tag], others: list[Kit], members) -> list[int]:
    """The champions not in the team who'd bring the check something it lacks."""
    return [
        i
        for i, kit in enumerate(others)
        if i not in members and ((kit.tags & check.counting) - tags or kit.tags & check.stacking)
    ]


def search(
    pinned: list[Kit],
    others: list[Kit],
    trials: list[Trial],
    needs: dict[int, tuple[Need, ...]],
    options: int,
) -> list[list[Kit]]:
    """Up to `options` sets of champions to add to `pinned`, best first: each the team
    clearing the most trials, then of the strongest champions, and each changing one of the
    newcomers a team before it needs (any newcomer, if it needs none)."""
    kits = pinned + others
    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    picked = [highs.addBinary() for _ in kits]
    cleared = {trial.skill: highs.addBinary() for trial in trials}
    highs.addConstr(highs.qsum(picked) <= TEAM_SIZE)

    for x in picked[: len(pinned)]:
        highs.addConstr(x == 1)

    for trial in trials:
        if trial.requires in cleared:
            highs.addConstr(cleared[trial.skill] <= cleared[trial.requires])

        for need in needs[trial.skill]:
            add_need(highs, need, trial.form, kits, picked, cleared[trial.skill])

    # A trial outweighs any team's strength (`strength` is under 1 per champion).
    objective = 10 * TEAM_SIZE * highs.qsum(cleared.values()) + highs.qsum(
        strength(kit.champion) * x for kit, x in zip(kits, picked, strict=True)
    )
    newcomer_vars = picked[len(pinned) :]
    found: list[list[Kit]] = []

    while len(found) < options:
        highs.maximize(objective)

        if highs.getModelStatus() != highspy.HighsModelStatus.kOptimal:
            break

        chosen = zip(others, newcomer_vars, strict=True)
        added = sorted((k for k, x in chosen if highs.val(x) > 0.5), key=lambda k: k.champion.name)
        if not added:
            break

        found.append(added)
        core = core_of(pinned + added, trials, needs, cleared_by(pinned + added, trials, needs))
        changeable = [kit for kit in added if kit in core] or added
        bar = [newcomer_vars[others.index(kit)] for kit in changeable]
        highs.addConstr(highs.qsum(bar) <= len(bar) - 1)

    return found


def cleared_by(kits: list[Kit], trials: list[Trial], needs: dict[int, tuple[Need, ...]]) -> int:
    return sum(cover.met for cover in trial_covers(kits, trials, needs))


def add_need(highs: highspy.Highs, need: Need, form: str, kits: list[Kit], picked, on) -> None:
    """Holds the need whenever `on` (the trial cleared) is 1."""
    match need:
        case Given():
            pass

        case AnyOf(tags=tags):
            bringing = [x for kit, x in zip(kits, picked, strict=True) if kit.tags & tags]
            highs.addConstr(highs.qsum(bringing) >= on)

        case Distinct(side=side, count=count, instances=instances):
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

            # A Poison on the team meets a count of debuff instances on its own.
            if instances:
                poisoning = highs.addBinary()
                stacks = stacking_tags(need)
                bringing = [x for kit, x in zip(kits, picked, strict=True) if kit.tags & stacks]
                highs.addConstr(poisoning <= highs.qsum(bringing))
                present.append(count * poisoning)

            highs.addConstr(highs.qsum(present) >= count * on)


def counts_toward(tag: Tag, need: Distinct, form: str) -> bool:
    """Whether the tag is one of the effects the need counts."""
    if tag.side != need.side or tag.name in need.excluded:
        return False

    return tag.side != Side.DEBUFF or tag.name not in immune_to(form)


def lineup_of(
    slots: list[Kit | None],
    suggested: set[int],
    trials: list[Trial],
    needs: dict[int, tuple[Need, ...]],
) -> Lineup:
    """The slots as members (`suggested`: the ids of the kits the search added), and what
    the team clears."""
    kits = [kit for kit in slots if kit]
    covers = trial_covers(kits, trials, needs)
    core = core_of(kits, trials, needs, sum(c.met for c in covers))
    members = tuple(
        Member(kit.champion, id(kit) not in suggested, kit in core) if kit else None
        for kit in slots
    )
    return Lineup(members, covers)


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
        case Given(need=inner, gear=gear):
            label = need_cover(inner, form, kits).label
            return NeedCover(label, True, (), (f"{gear} (any champion)",))

        case AnyOf(tags=tags):
            by = tuple(kit.champion for kit in kits if kit.tags & tags)
            label = " or ".join(sorted(tag_label(tag) for tag in tags))
            return NeedCover(label, bool(by), by)

        case Distinct(side=side, count=count, instances=instances):
            counted = [k for k in kits if any(counts_toward(t, need, form) for t in k.tags)]
            names = {t.name for k in counted for t in k.tags if counts_toward(t, need, form)}
            effects = tuple(sorted(STATUS_LABELS.get(n, spaced(n)) for n in names))
            where = "on the Chimera" if side == Side.DEBUFF else "on the team"

            if instances:
                poisoners = tuple(k.champion for k in kits if k.tags & stacking_tags(need))
                label = f"{count} {side}s {where} (Poisons stack: any Poison will do, if fast)"

                if poisoners:
                    return NeedCover(label, True, poisoners, ("Poison",))

                by = tuple(k.champion for k in counted)
                return NeedCover(label, len(names) >= count, by, effects)

            label = f"{count} different {side}s {where}"
            return NeedCover(
                label, len(names) >= count, tuple(k.champion for k in counted), effects
            )


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


def stacking_tags(need: Distinct) -> frozenset[Tag]:
    return frozenset(Tag(need.side, name) for name in STACKING)


def with_gear(needs: tuple[Need, ...], gear: tuple[Gear, ...]) -> tuple[Need, ...]:
    """The needs, those the gear meets for any team made `Given`."""
    return tuple(geared(need, gear) for need in needs)


def geared(need: Need, gear: tuple[Gear, ...]) -> Need:
    for piece in gear:
        match need:
            case AnyOf(tags=tags) if tags & piece.tags:
                return Given(need, piece.name)

            case Distinct(instances=True) if stacking_tags(need) & piece.tags:
                return Given(need, piece.name)

    return need


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
