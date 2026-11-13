"""
trials.py - the Chimera's trials for a column (Ultra Nightmare's), and what each asks of a team
(`trial_needs`, from the trial's rules, held against the game's own list of its statuses by
`check_needs`). The debuff-count trials count debuffs, not kinds: Poisons stack, so a team
placing them can reach the count if it's fast enough (Snake moves the Poisons on it to the
team each of its turns).

- `PARTS`, `ANIMAL_FORMS`, `LEVELS`, `PLAN_DIFFICULTY`, `TEAM_SIZE`: what's planned
- `AnyOf`, `Distinct`, `Given`, `Need`, `Requirement`, `Goals`: what a team must bring
- `column_trials`, `trial_needs`, `check_needs`: the trials and what they need
- `STACKING`, `stacking_tags`, `counts_toward`, `rule_count`: what they share
"""

import re
from dataclasses import dataclass

from optimiser.chimera.tags import (
    Mechanic,
    Side,
    Tag,
    buff,
    debuff,
    immune_to,
    status_kind,
)
from optimiser.enemies import Enemies, Trial

PARTS = ("Wing", "Tail", "Paw")  # the trial columns

ANIMAL_FORMS = ("Ram", "Lion", "Snake")  # the trial rows

LEVELS = ("Easy", "Normal", "Hard")

PLAN_DIFFICULTY = "UltraNightmare"

TEAM_SIZE = 5

# Status effects whose instances stack (Poisons): a team placing one can pile up a debuff
# count on its own, if it's fast enough (or extends them).
STACKING = frozenset({"ContinuousDamage"})


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
    """A need every team meets, thanks to `gear` (any champion can wear it), as far as
    `score` (its `Rating`)."""

    need: AnyOf | Distinct
    gear: str
    score: float


type Need = AnyOf | Distinct | Given


@dataclass(frozen=True)
class Requirement:
    """A need, and the Chimera form it's met in: its trial's ("" for an extra: any)."""

    need: Need
    form: str


@dataclass(frozen=True)
class Goals:
    """What a team is after: the column's trials (form by form, Easy first), what each needs,
    and `extras`: debuffs, buffs and effects wanted besides, in every team the search offers."""

    trials: tuple[Trial, ...]
    needs: dict[int, tuple[Need, ...]]
    extras: tuple[AnyOf, ...]

    def trial_requirements(self, trial: Trial) -> list[Requirement]:
        return [Requirement(need, trial.form) for need in self.needs[trial.skill]]

    @property
    def extra_requirements(self) -> list[Requirement]:
        return [Requirement(extra, "") for extra in self.extras]

    @property
    def requirements(self) -> list[Requirement]:
        """Every trial's, then the extras'."""
        trials = [r for trial in self.trials for r in self.trial_requirements(trial)]
        return trials + self.extra_requirements


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


def counts_toward(tag: Tag, need: Distinct, form: str) -> bool:
    """Whether the tag is one of the effects the need counts."""
    if tag.side != need.side or tag.name in need.excluded:
        return False

    return tag.side != Side.DEBUFF or tag.name not in immune_to(form)


def stacking_tags(need: Distinct) -> frozenset[Tag]:
    return frozenset(Tag(need.side, name) for name in STACKING)


def rule_count(trial: Trial, term: str) -> int:
    for rule in trial.rules:
        if match := re.search(re.escape(term) + r"(\d+)", rule):
            return int(match.group(1))

    raise ValueError(f"{trial.form} {trial.part} {trial.level}: no {term} in its rules")
