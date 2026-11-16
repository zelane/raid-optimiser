"""
plan.py - a column of trials as `optimiser.teams` goals, for the team finder to search with.

- `Brief`: what's asked
- `column_goals`: the goals, the trials by skill, and where they disagree with the game's data
"""

from dataclasses import dataclass

from optimiser.chimera.tags import ANY_FORM, form_target
from optimiser.chimera.trials import (
    PLAN_DIFFICULTY,
    TEAM_SIZE,
    check_needs,
    column_trials,
    trial_needs,
)
from optimiser.enemies import Enemies, Trial
from optimiser.teams.gear import Loadout, with_gear
from optimiser.teams.needs import AnyOf, Distinct, Goals, Objective
from optimiser.teams.tags import Tag


@dataclass(frozen=True)
class Brief:
    """What a team is asked for and has: the rotation's column at a tier (`difficulty`), what
    it must bring besides the trials (`wantable` tags; `counts`: so many different debuffs or
    buffs), and what it can wear or is assumed to have."""

    column: str
    wanted: tuple[Tag, ...]
    loadout: Loadout
    counts: tuple[Distinct, ...] = ()
    difficulty: str = PLAN_DIFFICULTY


def column_goals(enemies: Enemies, brief: Brief) -> tuple[Goals, dict[int, Trial], tuple[str, ...]]:
    """The column's nine trials as objectives (each met against its form, waiting on the one
    above it, keyed by its skill), what each needs (`Given` where gear any champion can wear
    meets it), what's wanted besides; the trials by skill, and where the needs disagree with
    the game's data."""
    trials = column_trials(enemies, brief.column, brief.difficulty)
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
