"""
plan.py - the team builder's entry points: what the champions in the slots clear
(`check_lineup`), and every way to fill the open slots (`fill_lineup`).

- `Brief`, `Plan`: what's asked, and the result
- `check_lineup`, `fill_lineup`: the workflows
- `slot_kits`, `column_goals`: what they share
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.chimera.tags import ANY_FORM, form_target
from optimiser.chimera.trials import TEAM_SIZE, check_needs, column_trials, trial_needs
from optimiser.enemies import Enemies, Trial
from optimiser.teams.cover import Lineup, lineup_of, ranking
from optimiser.teams.gear import Loadout, equip, with_gear
from optimiser.teams.kits import Kit, candidates, kit_of
from optimiser.teams.needs import AnyOf, Goals, Objective
from optimiser.teams.search import (
    PARTIAL_OPTIONS,
    SEARCH_BUDGET,
    every_team,
    partial_teams,
)
from optimiser.teams.tags import Tag


@dataclass(frozen=True)
class Brief:
    """What a team is asked for and has: the rotation's column, what it must bring besides the
    trials (`wantable` tags), and what it can wear or is assumed to have."""

    column: str
    wanted: tuple[Tag, ...]
    loadout: Loadout


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
    lineup = lineup_of(slot_kits(account, brief, slots), set(), goals)
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
    above: every smallest team clearing all the trials and bringing what's wanted (within
    `SEARCH_BUDGET`), the best scored first (`ranking`); the first `shown` of them as lineups.
    If none clears them all, a few teams clearing the most."""
    # 1. The column's nine trials, what each needs (less what the gear brings), and what's
    #    wanted besides.
    goals, trials, problems = column_goals(enemies, brief)

    # 2. Who's in the slots, and who could join them (the best copy of each champion), each
    #    with what they could wear or are assumed to bring.
    chosen = slot_kits(account, brief, slots)
    pinned = [kit for kit in chosen if kit]
    taken = {kit.champion.type_id // 10 for kit in pinned}
    others = [
        equip(kit_of(account, champion), brief.loadout)
        for champion in candidates(account, min_grade)
        if champion.type_id // 10 not in taken
    ]

    # 3. Every team clearing all the trials, or failing that the few clearing the most.
    found, complete = every_team(pinned, others, goals, SEARCH_BUDGET)
    partial = not found
    if partial:
        found = partial_teams(pinned, others, goals, PARTIAL_OPTIONS)
    else:
        found.sort(key=lambda added: ranking(pinned + added, goals))

    # 4. The first of them as lineups, each one's newcomers in the open slots in order.
    teams = []

    for added in found[:shown]:
        newcomers = iter(added)
        filled = [kit if kit else next(newcomers, None) for kit in chosen]
        teams.append(lineup_of(filled, {id(kit) for kit in added}, goals))

    return Plan(
        column=brief.column,
        trials=trials,
        lineup=lineup_of(chosen, set(), goals),
        options=tuple(teams),
        found=len(found),
        complete=complete,
        partial=partial,
        problems=problems,
        candidates=len(others),
    )


def slot_kits(
    account: Account, brief: Brief, slots: tuple[Champion | None, ...]
) -> list[Kit | None]:
    """The slots' champions' kits, with what they could wear or are assumed to bring."""
    return [equip(kit_of(account, c), brief.loadout) if c else None for c in slots]


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
    extras = tuple(AnyOf(frozenset({tag})) for tag in brief.wanted)
    goals = Goals(objectives, extras, ANY_FORM, TEAM_SIZE)
    return goals, {trial.skill: trial for trial in trials}, problems
