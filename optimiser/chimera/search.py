"""
search.py - finding teams: every smallest team clearing all the trials and bringing the extras
(`every_team`, up to a cap or a time budget), or failing that the few clearing the most (a
HiGHS MILP, `partial_teams`).

- `Budget`, `SEARCH_BUDGET`, `PARTIAL_OPTIONS`: how far it looks
- `every_team` (`Check`, `check_of`, `holds`, `bringing`): every team clearing them all
- `partial_teams` (`TeamModel`, `team_model`, `add_need`): the best partial teams
"""

import time
from dataclasses import dataclass

import highspy

from optimiser.chimera.cover import core_of, met_count
from optimiser.chimera.kits import Kit, strength
from optimiser.chimera.tags import Tag
from optimiser.chimera.trials import (
    TEAM_SIZE,
    AnyOf,
    Distinct,
    Given,
    Goals,
    Requirement,
    counts_toward,
    stacking_tags,
)


@dataclass(frozen=True)
class Budget:
    """How far `every_team` looks: so many teams, or so many seconds."""

    teams: int
    seconds: float


# Enough to rank well, quick enough for a page (with nothing pinned there are far more).
SEARCH_BUDGET = Budget(teams=20_000, seconds=1.0)

PARTIAL_OPTIONS = 3  # teams offered when none clears every trial


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
    goals: Goals,
    budget: Budget,
) -> tuple[list[list[Kit]], bool]:
    """Every smallest set of champions to add to `pinned` so the team clears all the trials
    and brings the extras (no one in it can be dropped), as many as the `budget` allows, and
    whether that's all there are. It adds, each time, a champion bringing the unmet need
    fewest can bring: every such set is reached, once."""
    open_slots = TEAM_SIZE - len(pinned)
    checks = [
        check_of(requirement, pinned + others)
        for requirement in goals.requirements
        if not isinstance(requirement.need, Given)
    ]
    base_tags = frozenset().union(*(kit.tags for kit in pinned))
    found: list[list[Kit]] = []
    visited: set[frozenset[int]] = set()
    deadline = time.monotonic() + budget.seconds
    stopped = False

    def clears(members: frozenset[int]) -> bool:
        tags = base_tags.union(*(others[i].tags for i in members))
        return all(holds(check, tags) for check in checks)

    def grow(members: frozenset[int], tags: frozenset[Tag]) -> None:
        nonlocal stopped

        if stopped or members in visited:
            return

        if len(found) >= budget.teams or time.monotonic() > deadline:
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


def check_of(requirement: Requirement, kits: list[Kit]) -> Check:
    """`requirement`'s need isn't `Given` (any team meets those)."""
    need, form = requirement.need, requirement.form
    match need:
        case AnyOf(tags=tags):
            return Check(tags, 1, frozenset())

        case Distinct(count=count, instances=instances):
            counting = {tag for kit in kits for tag in kit.tags if counts_toward(tag, need, form)}
            stacking = stacking_tags(need) if instances else frozenset()
            return Check(frozenset(counting), count, stacking)

    raise ValueError(f"no check for {need}")


def holds(check: Check, tags: frozenset[Tag]) -> bool:
    return bool(tags & check.stacking) or len(tags & check.counting) >= check.count


def bringing(check: Check, tags: frozenset[Tag], others: list[Kit], members) -> list[int]:
    """The champions not in the team who'd bring the check something it lacks."""
    return [
        i
        for i, kit in enumerate(others)
        if i not in members and ((kit.tags & check.counting) - tags or kit.tags & check.stacking)
    ]


def partial_teams(
    pinned: list[Kit],
    others: list[Kit],
    goals: Goals,
    options: int,
) -> list[list[Kit]]:
    """Up to `options` sets of champions to add to `pinned`, best first: each the team
    clearing the most trials (and bringing every extra), then of the strongest champions,
    and each changing one of the newcomers a team before it needs (any newcomer, if it needs
    none)."""
    model = team_model(pinned + others)
    highs, kits, picked = model.highs, model.kits, model.picked
    cleared = {trial.skill: highs.addBinary() for trial in goals.trials}

    for x in picked[: len(pinned)]:
        highs.addConstr(x == 1)

    for trial in goals.trials:
        if trial.requires in cleared:
            highs.addConstr(cleared[trial.skill] <= cleared[trial.requires])

        for requirement in goals.trial_requirements(trial):
            add_need(model, requirement, cleared[trial.skill])

    for requirement in goals.extra_requirements:
        add_need(model, requirement, 1)

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
        core = core_of(pinned + added, goals, met_count(pinned + added, goals))
        changeable = [kit for kit in added if kit in core] or added
        bar = [newcomer_vars[others.index(kit)] for kit in changeable]
        highs.addConstr(highs.qsum(bar) <= len(bar) - 1)

    return found


@dataclass(frozen=True)
class TeamModel:
    """The MILP choosing a team: a binary per kit (`picked`), at most `TEAM_SIZE` of them."""

    highs: highspy.Highs
    kits: list[Kit]
    picked: list[highspy.highs_var]


def team_model(kits: list[Kit]) -> TeamModel:
    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    picked = [highs.addBinary() for _ in kits]
    highs.addConstr(highs.qsum(picked) <= TEAM_SIZE)
    return TeamModel(highs, kits, picked)


def add_need(model: TeamModel, requirement: Requirement, on) -> None:
    """Holds the need whenever `on` (the trial cleared; 1 for an extra) is 1."""
    highs, kits, picked = model.highs, model.kits, model.picked
    need, form = requirement.need, requirement.form
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
