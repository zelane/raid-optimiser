"""
trials.py - the Chimera's trials for a column (Ultra Nightmare's), and what each asks of a team
(`trial_needs`, from the trial's rules, held against the game's own list of its statuses by
`check_needs`), as `optimiser.teams` needs. The debuff-count trials count debuffs, not kinds:
Poisons stack, so a team placing them can reach the count if it's fast enough (Snake moves
the Poisons on it to the team each of its turns). They pile up over the fight
(`Distinct.accumulates`: the team gets several turns to each of the Chimera's), so any Poison
source meets them, given speed.

- `PARTS`, `ANIMAL_FORMS`, `LEVELS`, `PLAN_DIFFICULTY`, `TEAM_SIZE`: what's planned
- `column_trials`, `trial_needs`, `check_needs`, `rule_count`: the trials and what they need
"""

import re

from optimiser.chimera.tags import immune_to
from optimiser.enemies import Enemies, Trial
from optimiser.teams.needs import AnyOf, Distinct, Need
from optimiser.teams.tags import Mechanic, Side, Tag, buff, debuff, status_kind

PARTS = ("Wing", "Tail", "Paw")  # the trial columns

ANIMAL_FORMS = ("Ram", "Lion", "Snake")  # the trial rows

LEVELS = ("Easy", "Normal", "Hard")

PLAN_DIFFICULTY = "UltraNightmare"

TEAM_SIZE = 5


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
            piled = Distinct(Side.DEBUFF, count, instances=True, accumulates=True)
            return (AnyOf(buff("IncreaseDefence")), piled)
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
                Distinct(Side.DEBUFF, count, instances=True, accumulates=True),
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
            excluded = frozenset({"BlockActiveSkills"})
            return (Distinct(Side.DEBUFF, count, True, excluded, accumulates=True),)
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


def rule_count(trial: Trial, term: str) -> int:
    for rule in trial.rules:
        if match := re.search(re.escape(term) + r"(\d+)", rule):
            return int(match.group(1))

    raise ValueError(f"{trial.form} {trial.part} {trial.level}: no {term} in its rules")
