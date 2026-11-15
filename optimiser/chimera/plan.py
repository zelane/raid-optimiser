"""
plan.py - the team builder's entry points: what the champions in the slots clear
(`check_lineup`), and every way to fill the open slots (`fill_lineup`).

- `Brief`, `Plan`: what's asked, and the result
- `check_lineup`, `fill_lineup`: the workflows (`teams.find` does the finding)
- `column_goals`: what they share
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.chimera.tags import ANY_FORM, form_target
from optimiser.chimera.trials import TEAM_SIZE, check_needs, column_trials, trial_needs
from optimiser.enemies import Enemies, Trial
from optimiser.teams.cover import Lineup
from optimiser.teams.find import Worn, check_slots, find_teams
from optimiser.teams.gear import Loadout, with_gear
from optimiser.teams.kits import candidates
from optimiser.teams.needs import AnyOf, Distinct, Goals, Objective
from optimiser.teams.tags import Tag


@dataclass(frozen=True)
class Brief:
    """What a team is asked for and has: the rotation's column, what it must bring besides the
    trials (`wantable` tags; `counts`: so many different debuffs or buffs), and what it can
    wear (`worn`: each slot's relics) or is assumed to have."""

    column: str
    wanted: tuple[Tag, ...]
    loadout: Loadout
    counts: tuple[Distinct, ...] = ()
    worn: Worn = ()  # each slot's relics


@dataclass(frozen=True)
class Plan:
    """The slots as the user filled them, and (when the search ran) the teams it found
    keeping them, best first: `found` in all (`complete`: no more exist), `options` the
    first of them. `partial`: none clears every trial, so these clear the most they can.
    `trials`: the column's, by skill (each lineup's objectives are keyed by it)."""

    column: str
    trials: dict[int, Trial]
    lineup: Lineup
    options: tuple[Lineup, ...]
    found: int
    complete: bool
    partial: bool
    problems: tuple[str, ...]  # trials whose needs disagree with the game's data
    candidates: int = 0  # champions the search could add (0 when it didn't run)


def check_lineup(
    account: Account, enemies: Enemies, brief: Brief, slots: tuple[Champion | None, ...]
) -> Plan:
    """What the champions in the slots clear on their own, and which of the wanted debuffs,
    buffs and effects they bring."""
    goals, trials, problems = column_goals(enemies, brief)
    lineup = check_slots(account, brief.loadout, slots, goals, brief.worn)
    return Plan(
        brief.column, trials, lineup, (), 0, complete=True, partial=False, problems=problems
    )


def fill_lineup(
    account: Account,
    enemies: Enemies,
    brief: Brief,
    slots: tuple[Champion | None, ...],
    min_grade: int,
    shown: int,
) -> Plan:
    """The slots' champions kept, the open slots filled with champions at `min_grade`★ or
    above (the best copy of each): every smallest team clearing all the trials and bringing
    what's wanted (`teams.find_teams`), the first `shown` of them as lineups. If none clears
    them all, a few teams clearing the most."""
    goals, trials, problems = column_goals(enemies, brief)
    pool = candidates(account, min_grade)
    found = find_teams(account, brief.loadout, slots, goals, pool, shown, brief.worn)
    return Plan(
        column=brief.column,
        trials=trials,
        lineup=found.lineup,
        options=found.options,
        found=found.found,
        complete=found.complete,
        partial=found.partial,
        problems=problems,
        candidates=found.candidates,
    )


def column_goals(enemies: Enemies, brief: Brief) -> tuple[Goals, dict[int, Trial], tuple[str, ...]]:
    """The column's nine trials as objectives (each met against its form, waiting on the one
    above it), what each needs (`Given` where gear any champion can wear meets it), what's
    wanted besides; the trials by skill, and where the needs disagree with the game's data."""
    trials = column_trials(enemies, brief.column)
    needs = {trial.skill: trial_needs(trial) for trial in trials}
    problems = tuple(
        problem for trial in trials if (problem := check_needs(trial, needs[trial.skill]))
    )
    gear = brief.loadout.team_gear
    objectives = tuple(
        Objective(
            trial.skill,
            form_target(trial.form),
            with_gear(needs[trial.skill], gear),
            trial.requires,
        )
        for trial in trials
    )
    extras = tuple(AnyOf(frozenset({tag})) for tag in brief.wanted) + brief.counts
    goals = Goals(objectives, extras, ANY_FORM, TEAM_SIZE)
    return goals, {trial.skill: trial for trial in trials}, problems
