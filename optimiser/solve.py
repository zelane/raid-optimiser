"""
solve.py - the best builds for a champion: stat limits and set minimums met, then stats
maximised in the order asked, each held within a slack of its best before the next.

A build is one artifact per armour slot and at most one per accessory slot. Every stat is
a per-champion constant plus a sum over the pieces chosen; set bonuses are exact through
piece-count variables. So each step is a MILP, solved with HiGHS.

A ranked goal is a stat, or a skill's damage (`DamageGoal`). Damage is a product, so it's
ranked by its log: log(formula) + log(1 + C.DMG) + log(DEF multiplier). The first two are
concave, held under tangent lines; the third depends only on the DEF the sets ignore, which
comes in 5 % steps, so it's exact with a binary per step.

- `GearFilter`, `Goal`, `Request`: what's asked
- `Build`, `SetsRuleOut`, `Shortfall`: the outcomes
- `find_builds`: the workflow
- `frame` (`wearable`, `prune`, `directions`), `check_sets`, `best_build`,
  `explain_shortfall` (`best_alone`): its steps, in the order it calls them
- `Problem`, `Milp`, `Expression`, `SetTerms`, `formulate`, `set_terms`, `add_limits`,
  `Ranked`, `ranked`, `hold`, `maximise`: the model the steps share
- `log_damage`, `reach`, `geometric_points`, `even_points`, `log_under_tangents`,
  `log_defence_multiplier`: the damage goal
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import highspy

from optimiser.account import (
    ARMOUR,
    Account,
    Artifact,
    ArtifactSet,
    Champion,
    FixedSet,
    Locks,
    Slot,
    Stat,
    Stats,
    Tables,
    VariableSet,
)
from optimiser.damage import ActiveIgnore, DamageGoal, LinearFormula, applies, defence_multiplier
from optimiser.reserve import Reservations, Rule
from optimiser.stats import (
    artifact_stats,
    base_stats,
    build_stats,
    constant_stats,
    set_multiplier,
    set_stats,
)

MAX_PIECES = 9
# Ranking past these is wasted: crit rate stops at 100 %.
RANK_CAPS = {Stat.CR: 1.0}
IGNORE_STEP = 0.05  # every set's ignore DEF is a multiple of this
# Tangent lines per log term, spread over the range a build can reach. Fewer, tighter
# tangents solve several times faster; between them log is overstated by ~0.1-0.2 %, and
# reported damage is always recomputed exactly.
TANGENTS = 20
SET_HEADROOM = 1.5  # sets can add to what the best piece per slot gives


@dataclass(frozen=True)
class GearFilter:
    """Which gear a solve may not take, each part on its own; nothing set: any gear. The
    champion's own is always allowed.

    `unworn_only`: nothing another champion wears. `lock_level`: nothing worn by a champion
    locked above it (0: only unlocked champions'; None: locks don't matter). `reserved`: what
    the `rules` keep (`optimiser.reserve`), worn or not."""

    unworn_only: bool = False
    lock_level: int | None = None
    locks: Locks = field(default_factory=dict)
    rules: tuple[Rule, ...] = ()
    reserved: Reservations = field(default_factory=dict)

    def allows(self, artifact_id: int, owner: int | None) -> bool:
        """`owner`: whoever wears it, if anyone but the champion does."""
        if artifact_id in self.reserved:
            return False

        if owner is None:
            return True

        if self.unworn_only:
            return False

        return self.lock_level is None or self.locks.get(owner, 0) <= self.lock_level


type Goal = Stat | DamageGoal


@dataclass(frozen=True)
class Request:
    """Limits are inclusive. `ranking` is never empty: the first goal matters most."""

    champion: Champion
    minimums: Stats
    maximums: Stats
    set_minimums: dict[int, int]  # set id -> pieces
    ranking: tuple[Goal, ...]
    slack: float  # each ranked stat may give up this fraction of its best for the next
    builds: int
    gear: GearFilter
    above_level: int  # only pieces enhanced past this level (8: +9 and up)

    def damage_goal(self) -> DamageGoal | None:
        """The skill damage ranked, if any is."""
        return next((goal for goal in self.ranking if isinstance(goal, DamageGoal)), None)


@dataclass(frozen=True)
class Build:
    artifacts: tuple[Artifact, ...]
    stats: Stats


@dataclass(frozen=True)
class SetsRuleOut:
    """No build meets the request: the set minimums alone rule it out."""

    reason: str


@dataclass(frozen=True)
class Shortfall:
    """No build meets the request's limits: the best each minimum can reach and the lowest
    each maximum can, each on its own with the sets asked."""

    highest: dict[Stat, float]
    lowest: dict[Stat, float]


@dataclass(frozen=True)
class Problem:
    """What the model is built from: the pieces the champion can wear and what each adds."""

    champion: Champion
    tables: Tables
    base: Stats
    constant: Stats
    pieces: tuple[Artifact, ...]
    piece_stats: dict[int, Stats]  # artifact id -> what it adds
    sets: dict[int, ArtifactSet]  # the sets among the pieces
    set_multiplier: float


def find_builds(account: Account, request: Request) -> list[Build] | SetsRuleOut | Shortfall:
    """Up to `request.builds` builds, best first, no two alike."""
    # 1. What the champion can wear, and what each piece adds.
    problem = frame(account, request)

    # 2. Too few pieces of a required set: no need to solve.
    if reason := check_sets(problem, request):
        return SetsRuleOut(reason)

    # 3. The best build, then the best unlike any found so far, until enough or none left.
    builds: list[Build] = []
    while len(builds) < request.builds and (build := best_build(problem, request, builds)):
        builds.append(build)

    # 4. None meets the limits: how close each limited stat can get.
    if not builds:
        return explain_shortfall(problem, request)

    return builds


def frame(account: Account, request: Request) -> Problem:
    champion = request.champion
    tables = account.tables
    base = base_stats(champion, tables)
    wearing = [a for a in account.artifacts if wearable(a, account, request)]
    piece_stats = {a.id: artifact_stats(a, base) for a in wearing}
    pieces = prune(wearing, piece_stats, request)

    return Problem(
        champion=champion,
        tables=tables,
        base=base,
        constant=constant_stats(champion, tables),
        pieces=pieces,
        piece_stats={a.id: piece_stats[a.id] for a in pieces},
        sets={a.set_id: tables.sets[a.set_id] for a in pieces if a.set_id in tables.sets},
        set_multiplier=set_multiplier(champion, tables),
    )


def wearable(artifact: Artifact, account: Account, request: Request) -> bool:
    if artifact.faction not in (None, request.champion.faction):
        return False

    if artifact.level <= request.above_level:
        return False

    if (owner := account.owners.get(artifact.id)) == request.champion.id:
        return True

    return request.gear.allows(artifact.id, owner)


def prune(
    pieces: list[Artifact], piece_stats: dict[int, Stats], request: Request
) -> tuple[Artifact, ...]:
    """Drop pieces that at least `request.builds` others in the same slot, set and faction
    lock match or beat on every stat the request uses: swapping one of those in never makes
    a build worse, so the best builds never need it."""
    wanted = directions(request)
    groups: dict[tuple, list[Artifact]] = {}

    for artifact in pieces:
        groups.setdefault((artifact.slot, artifact.set_id, artifact.faction), []).append(artifact)

    def at_least_as_good(better: Artifact, worse: Artifact) -> bool:
        ours, theirs = piece_stats[better.id], piece_stats[worse.id]
        return all(
            (ours[stat] - theirs[stat]) * way >= 0 if way else ours[stat] == theirs[stat]
            for stat, way in wanted.items()
        )

    kept = []

    for group in groups.values():
        for index, artifact in enumerate(group):
            # Ties: an identical piece earlier in the group counts as better.
            beaten_by = sum(
                1
                for other_index, other in enumerate(group)
                if other is not artifact
                and at_least_as_good(other, artifact)
                and (other_index < index or not at_least_as_good(artifact, other))
            )

            if beaten_by < request.builds:
                kept.append(artifact)

    return tuple(kept)


def directions(request: Request) -> dict[Stat, int]:
    """Each stat the request uses: +1 more is better, -1 less is better, 0 must match."""
    wanted: dict[Stat, int] = {stat: 1 for stat in request.minimums}

    for goal in request.ranking:
        match goal:
            case DamageGoal(formula=formula):
                wanted |= {stat: 1 for stat in formula.coefficients} | {Stat.CD: 1}

            case stat:
                wanted[stat] = 1

    for stat in request.maximums:
        wanted[stat] = 0 if stat in wanted else -1

    return wanted


def check_sets(problem: Problem, request: Request) -> str | None:
    """Why the set minimums can't be met, if too few pieces are wearable."""
    for set_id, minimum in request.set_minimums.items():
        available = sum(1 for a in problem.pieces if a.set_id == set_id)

        if available < minimum:
            name = problem.tables.sets[set_id].name
            return f"{minimum} {name} pieces asked, {available} wearable"

    return None


def best_build(problem: Problem, request: Request, excluded: list[Build]) -> Build | None:
    """The best build unlike any in `excluded`, or None if no other meets the limits."""
    milp = formulate(problem, request.set_minimums, excluded)
    add_limits(milp, request)

    for goal in request.ranking:
        objective = ranked(milp, goal, problem)

        if (best := maximise(milp, objective.expression)) is None:
            return None

        hold(milp, objective, best, request.slack)

    picked = tuple(a for a in problem.pieces if milp.highs.val(milp.chosen[a.id]) > 0.5)
    return Build(picked, build_stats(problem.champion, picked, problem.tables))


def explain_shortfall(problem: Problem, request: Request) -> SetsRuleOut | Shortfall:
    """Each limited stat on its own, with only the set minimums asked."""
    highest: dict[Stat, float] = {}
    lowest: dict[Stat, float] = {}

    for stat in request.minimums:
        if (best := best_alone(problem, request, stat, way=1)) is None:
            return SetsRuleOut("the set minimums can't be met together")

        highest[stat] = best

    for stat in request.maximums:
        if (best := best_alone(problem, request, stat, way=-1)) is None:
            return SetsRuleOut("the set minimums can't be met together")

        lowest[stat] = best

    return Shortfall(highest, lowest)


def best_alone(problem: Problem, request: Request, stat: Stat, way: int) -> float | None:
    """The highest (`way` 1) or lowest (-1) the stat reaches with only the set minimums asked;
    None if they can't be met."""
    milp = formulate(problem, request.set_minimums, [])
    best = maximise(milp, way * milp.stats[stat])
    return None if best is None else way * best


type Expression = highspy.highs_linear_expression | highspy.highs_var


@dataclass(frozen=True)
class Milp:
    """A HiGHS model of one champion's builds: a binary per piece, and each stat as an
    expression of them."""

    highs: highspy.Highs
    chosen: dict[int, highspy.highs_var]  # artifact id -> 1 if worn
    stats: dict[Stat, highspy.highs_linear_expression]
    ignore: list[ActiveIgnore[Expression]]


@dataclass(frozen=True)
class SetTerms:
    """What a set adds to the model: to each stat, and the ignore-DEF passives it turns on."""

    stats: Sequence[tuple[Stat, Expression]]
    ignore: Sequence[ActiveIgnore[Expression]]


def formulate(problem: Problem, set_minimums: dict[int, int], excluded: list[Build]) -> Milp:
    highs = highspy.Highs()
    highs.silent()
    chosen = {a.id: highs.addBinary() for a in problem.pieces}
    terms: dict[Stat, list] = {stat: [] for stat in Stat}
    ignore: list[ActiveIgnore[Expression]] = []

    for slot in Slot:
        if in_slot := [chosen[a.id] for a in problem.pieces if a.slot == slot]:
            worn = highs.qsum(in_slot)
            highs.addConstr(worn == 1 if slot in ARMOUR else worn <= 1)

    for artifact in problem.pieces:
        for stat, amount in problem.piece_stats[artifact.id].items():
            if amount:
                terms[stat].append(amount * chosen[artifact.id])

    for set_id, artifact_set in problem.sets.items():
        count = highs.qsum(chosen[a.id] for a in problem.pieces if a.set_id == set_id)

        if minimum := set_minimums.get(set_id):
            highs.addConstr(count >= minimum)

        added = set_terms(highs, artifact_set, count, problem)
        ignore += added.ignore

        for stat, term in added.stats:
            terms[stat].append(term)

    for build in excluded:
        highs.addConstr(
            highs.qsum(chosen[a.id] for a in build.artifacts) <= len(build.artifacts) - 1
        )

    stats = {stat: highs.qsum(terms[stat]) + problem.constant[stat] for stat in Stat}
    return Milp(highs, chosen, stats, ignore)


def set_terms(
    highs: highspy.Highs, artifact_set: ArtifactSet, count: Expression, problem: Problem
) -> SetTerms:
    """What the set adds, given the expression counting its pieces. Piece-count variables are
    tied to `count` exactly, so a stat maximum can't hide a bonus."""
    base, multiplier = problem.base, problem.set_multiplier

    match artifact_set:
        case FixedSet(pieces=pieces, ignore=ignore):
            per_set = set_stats(artifact_set, pieces, base, multiplier)
            if not any(per_set.values()) and not ignore:
                return SetTerms([], [])

            times = highs.addIntegral(lb=0, ub=MAX_PIECES // pieces)
            highs.addConstr(pieces * times <= count)
            highs.addConstr(pieces * times >= count - (pieces - 1))
            stat_terms = [(stat, amount * times) for stat, amount in per_set.items() if amount]
            return SetTerms(stat_terms, [ActiveIgnore(source, times) for source in ignore])

        case VariableSet(ignore_at=ignore_at):
            totals = {
                pieces: set_stats(artifact_set, pieces, base, multiplier)
                for pieces in range(1, MAX_PIECES + 1)
            }
            if not any(any(t.values()) for t in totals.values()) and not ignore_at:
                return SetTerms([], [])

            exactly = {pieces: highs.addBinary() for pieces in range(MAX_PIECES + 1)}
            highs.addConstr(highs.qsum(exactly.values()) == 1)
            highs.addConstr(highs.qsum(k * at for k, at in exactly.items()) == count)
            stat_terms = [
                (stat, amount * exactly[pieces])
                for pieces, total in totals.items()
                for stat, amount in total.items()
                if amount
            ]
            ignore_terms: list[ActiveIgnore[Expression]] = [
                ActiveIgnore(source, exactly[pieces])
                for pieces in range(1, MAX_PIECES + 1)
                if (reached := [tier for tier in ignore_at if tier <= pieces])
                for source in ignore_at[max(reached)]
            ]
            return SetTerms(stat_terms, ignore_terms)


def add_limits(milp: Milp, request: Request) -> None:
    for stat, minimum in request.minimums.items():
        milp.highs.addConstr(milp.stats[stat] >= minimum)

    for stat, maximum in request.maximums.items():
        milp.highs.addConstr(milp.stats[stat] <= maximum)


@dataclass(frozen=True)
class Ranked:
    """A goal as the solver maximises it; `log` when that's the log of the goal."""

    expression: Expression
    log: bool


def ranked(milp: Milp, goal: Goal, problem: Problem) -> Ranked:
    match goal:
        case DamageGoal():
            return Ranked(log_damage(milp, goal, problem), log=True)

        case stat if (cap := RANK_CAPS.get(stat)) is not None:
            capped = milp.highs.addVariable(lb=-highspy.kHighsInf, ub=cap)
            milp.highs.addConstr(capped <= milp.stats[stat])
            return Ranked(capped, log=False)  # more is wasted past the cap

        case stat:
            return Ranked(milp.stats[stat], log=False)


def hold(milp: Milp, objective: Ranked, best: float, slack: float) -> None:
    """Keep the goal within `slack` of its best while later goals are maximised."""
    floor = best + math.log(1 - slack) if objective.log else best - slack * abs(best)
    milp.highs.addConstr(objective.expression >= floor)


def log_damage(milp: Milp, goal: DamageGoal, problem: Problem):
    """log(damage), less log(1 + books), which gear doesn't change."""
    highs = milp.highs
    formula = goal.formula.constant + highs.qsum(
        k * milp.stats[stat] for stat, k in goal.formula.coefficients.items()
    )
    gear_formula = LinearFormula(goal.formula.coefficients)  # what a piece adds to it
    low, high = reach(problem, goal.formula.value(problem.constant), gear_formula.value)
    crit_low, crit_high = reach(problem, problem.constant[Stat.CD], lambda s: s[Stat.CD])

    log_formula = log_under_tangents(highs, formula, geometric_points(max(low, 1.0), high))
    log_crit = log_under_tangents(
        highs, 1 + milp.stats[Stat.CD], even_points(1 + crit_low, 1 + crit_high)
    )
    return log_formula + log_crit + log_defence_multiplier(milp, goal)


def reach(problem: Problem, gearless: float, adds) -> tuple[float, float]:
    """From gearless to roughly the most a build could reach: the best piece per slot, with
    headroom for sets. Only sets the tangents' spread, so a rough top is fine."""
    best_per_slot = sum(
        max((adds(problem.piece_stats[a.id]) for a in problem.pieces if a.slot == slot), default=0)
        for slot in Slot
    )
    return gearless, gearless + max(best_per_slot, 0) * SET_HEADROOM + 1


def geometric_points(low: float, high: float) -> list[float]:
    """`TANGENTS` points from `low` to `high`, each the same ratio past the last."""
    return [low * (high / low) ** (step / (TANGENTS - 1)) for step in range(TANGENTS)]


def even_points(low: float, high: float) -> list[float]:
    """`TANGENTS` points from `low` to `high`, evenly apart."""
    return [low + (high - low) * step / (TANGENTS - 1) for step in range(TANGENTS)]


def log_under_tangents(highs: highspy.Highs, expression, points: list[float]):
    """A variable held under log(expression) by its tangents at `points`; maximising pushes
    it up to the curve (log is concave, so tangents lie above it)."""
    log = highs.addVariable(lb=-highspy.kHighsInf)

    for point in points:
        highs.addConstr(log <= math.log(point) + (expression - point) / point)

    return log


def log_defence_multiplier(milp: Milp, goal: DamageGoal):
    """log(DEF multiplier), exact: the sets' ignore DEF is a multiple of IGNORE_STEP, so a
    binary per step carries its exact value. Passives granted by several sets count once
    unless they stack per set."""
    highs = milp.highs
    by_skill: dict[int, list[ActiveIgnore[Expression]]] = {}

    for passive in milp.ignore:
        if applies(goal, passive.source):
            by_skill.setdefault(passive.source.skill_id, []).append(passive)

    parts = []
    most = 0.0

    for group in by_skill.values():
        source = group[0].source
        active = highs.qsum(passive.times for passive in group)

        if source.per_set:
            parts.append(source.value * active)
            most += source.value * MAX_PIECES
        else:
            once = highs.addBinary()
            highs.addConstr(once <= active)
            parts.append(source.value * once)
            most += source.value

        if abs(source.value / IGNORE_STEP - round(source.value / IGNORE_STEP)) > 1e-9:
            raise ValueError(f"ignore DEF {source.value} isn't a multiple of {IGNORE_STEP}")

    steps = range(round(most / IGNORE_STEP) + 1)
    at_step = [highs.addBinary() for _ in steps]
    highs.addConstr(highs.qsum(at_step) == 1)
    # At most what the sets give: the term rises with ignore DEF, so maximising takes the
    # highest step allowed, and step 0 is always feasible (an equality makes HiGHS struggle
    # to find a first solution).
    highs.addConstr(
        highs.qsum(IGNORE_STEP * step * at for step, at in zip(steps, at_step, strict=True))
        <= highs.qsum(parts)
    )
    return highs.qsum(
        math.log(defence_multiplier(goal.enemy_defence, goal.skill_ignore + IGNORE_STEP * step))
        * at
        for step, at in zip(steps, at_step, strict=True)
    )


def maximise(milp: Milp, goal) -> float | None:
    """The best value of `goal`, leaving its solution in the model; None if infeasible."""
    milp.highs.maximize(goal)

    if milp.highs.getModelStatus() != highspy.HighsModelStatus.kOptimal:
        return None

    return milp.highs.val(goal)
