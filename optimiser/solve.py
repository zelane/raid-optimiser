"""
solve.py - the best builds for a champion, or a build each for a team: stat limits and set
minimums met, then stats maximised in the order asked, each held within a slack of its best
before the next. A team's champions go in order: each gets its best of what the earlier ones
left, as long as the later ones can still meet their limits.

A build is one artifact per armour slot and at most one per accessory slot; in a team, no
piece goes to two champions. Every stat is a per-champion constant plus a sum over the
pieces chosen; set bonuses are exact through piece-count variables. So each step is a MILP,
solved with HiGHS (a team's limits checked in one model).

A ranked goal is a stat, a skill's damage (`DamageGoal`), or a rate (`accuracy.RateGoal`: debuffs
landing against a RES, or resisting an ACC). A rate is ranked as its stat, capped where the
rate stops rising (as C.RATE is at 100 %), and held within the slack of its best rate, not
stat: the least stat for that rate. Damage is a product, so it's
ranked by its log: log(formula) + log(1 + C.DMG) + log(1 + sets' damage bonus) + log(DEF
multiplier). The first three are concave, held under tangent lines (the bonus's at every total
it can reach, so exact); the last depends only on the DEF the sets ignore, which comes in 5 %
steps, so it's exact with a binary per step.

A solve can be stopped (`stop`, from another thread, even before it reaches its first HiGHS
solve): the running HiGHS solve is interrupted and no more start. One champion's builds
found by then are kept; else the outcome is `Stopped`.

- `GearFilter`, `Goal`, `Request`, `Member`: what's asked
- `Build`, `SetsRuleOut`, `Shortfall`, `Unmet`, `Clash`, `Stopped`: the outcomes
- `find_builds` (one champion), `find_team_builds` (several): the workflows
- `stop`, `Interrupted`, `STOPPING`, `interrupt`, `check_stopped`: stopping a solve
- `frame` (`wearable`, `prune`, `directions`), `check_sets`, `best_build`
  (`maximise_ranking`, `solved_build`), `explain_shortfall` (`best_alone`): one champion's
  steps, in the order they're called
- `feasible`, `best_leaving` (`best_together`), `why_unmet`: a team's
- `Problem`, `Milp`, `Expression`, `SetTerms`, `formulate`, `add_member`, `set_terms`,
  `add_limits`, `Ranked`, `ranked`, `hold`, `maximise`: the model the steps share
- `log_damage`, `reach`, `geometric_points`, `even_points`, `log_under_tangents`,
  `log_damage_bonus`, `log_defence_multiplier` (`most_ignore`, `ignore_total`): the damage goal
"""

import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

import highspy

from optimiser.account import Account, Artifact, Champion, Locks, slot_unlocked
from optimiser.accuracy import Lands, RateGoal, Resists
from optimiser.battle import Battle
from optimiser.damage import (
    ActiveBonus,
    ActiveIgnore,
    DamageGoal,
    LinearFormula,
    applies,
    defence_multiplier,
)
from optimiser.reserve import Reservations, Rule
from optimiser.stats import (
    artifact_stats,
    base_stats,
    build_stats,
    constant_stats,
    set_multiplier,
    set_stats,
)
from optimiser.tables import (
    ARMOUR,
    ArtifactSet,
    Bonus,
    FixedSet,
    Slot,
    Stat,
    Stats,
    Tables,
    VariableSet,
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
LEAVING_TRIES = 3  # a team member's builds tried alone before solving with the rest
STOPPING = threading.Event()  # set by `stop`, cleared as a workflow ends


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


type Goal = Stat | DamageGoal | RateGoal


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
    battle: Battle = Battle()  # buffs and an aura assumed on the champion

    def damage_goal(self) -> DamageGoal | None:
        """The skill damage ranked, if any is."""
        return next((goal for goal in self.ranking if isinstance(goal, DamageGoal)), None)


@dataclass(frozen=True)
class Member:
    """A team's champion: their request, against the account as assumed for it (glyphs go
    only on what the request wants)."""

    account: Account
    request: Request


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
class Clash:
    """Each champion can be geared alone, but not all of them together."""


@dataclass(frozen=True)
class Stopped:
    """The solve was stopped before it found anything."""


@dataclass(frozen=True)
class Unmet:
    """No team build: per member, why they can't be geared even alone (None: they can)."""

    members: tuple[SetsRuleOut | Shortfall | None, ...]


@dataclass(frozen=True)
class Problem:
    """What the model is built from: the pieces the champion can wear and what each adds."""

    champion: Champion
    tables: Tables
    base: Stats
    battle: tuple[Bonus, ...]  # what the battle assumed adds (`Battle.bonuses`)
    constant: Stats
    pieces: tuple[Artifact, ...]
    piece_stats: dict[int, Stats]  # artifact id -> what it adds
    sets: dict[int, ArtifactSet]  # the sets among the pieces
    set_multiplier: float


def find_builds(
    account: Account, request: Request
) -> list[Build] | SetsRuleOut | Shortfall | Stopped:
    """Up to `request.builds` builds, best first, no two alike; if stopped, those found."""
    try:
        return builds_for(account, request)

    except Interrupted as stopped:
        return stopped.builds or Stopped()

    finally:
        STOPPING.clear()


def builds_for(account: Account, request: Request) -> list[Build] | SetsRuleOut | Shortfall:
    """`find_builds`' steps; `Interrupted` carries the builds found if stopped."""
    # 1. What the champion can wear, and what each piece adds.
    problem = frame(account, request, frozenset({request.champion.id}), request.builds)

    # 2. Too few pieces of a required set: no need to solve.
    if reason := check_sets(problem, request):
        return SetsRuleOut(reason)

    # 3. The best build, then the best unlike any found so far, until enough or none left.
    builds: list[Build] = []

    try:
        while len(builds) < request.builds and (build := best_build(problem, request, builds)):
            builds.append(build)

    except Interrupted:
        raise Interrupted(builds) from None

    # 4. None meets the limits: how close each limited stat can get.
    if not builds:
        return explain_shortfall(problem, request)

    return builds


def find_team_builds(members: Sequence[Member]) -> tuple[Build, ...] | Unmet | Clash | Stopped:
    """A build per member, in order, no piece in two: each member's best of what the earlier
    ones left that still leaves the later ones their limits. (Solving the team as one model,
    each goal held before the next, gave much the same and took minutes: proving each step
    optimal over every champion's pieces at once.)"""
    try:
        return team_builds(members)

    except Interrupted:
        return Stopped()

    finally:
        STOPPING.clear()


def team_builds(members: Sequence[Member]) -> tuple[Build, ...] | Unmet | Clash:
    """`find_team_builds`' steps."""
    team = frozenset(member.request.champion.id for member in members)

    # 1. Can they all meet their limits at once? If not, who can't even alone.
    if not feasible(members, team, frozenset()):
        return why_unmet(members, team)

    # 2. In order, each member's best build leaving the rest feasible.
    taken: frozenset[int] = frozenset()
    builds: list[Build] = []

    for index, member in enumerate(members):
        build = best_leaving(member, members[index + 1 :], team, taken)
        builds.append(build)
        taken |= {a.id for a in build.artifacts}

    return tuple(builds)


def feasible(members: Sequence[Member], team: frozenset[int], taken: frozenset[int]) -> bool:
    """Whether the members meet their limits together, from what isn't `taken`."""
    problems = [frame(m.account, m.request, team, len(members), taken) for m in members]

    if any(check_sets(p, m.request) for p, m in zip(problems, members, strict=True)):
        return False

    milps = formulate(problems, [m.request.set_minimums for m in members])

    for milp, member in zip(milps, members, strict=True):
        add_limits(milp, member.request)

    milps[0].highs.run()
    check_stopped()
    return milps[0].highs.getModelStatus() == highspy.HighsModelStatus.kOptimal


def best_leaving(
    member: Member, rest: Sequence[Member], team: frozenset[int], taken: frozenset[int]
) -> Build:
    """The member's best build from what isn't `taken` that leaves `rest` feasible: their best
    alone, else their next best, `LEAVING_TRIES` in all, else the best with the rest solved
    alongside (slow, but exact). The rest was feasible with the member, so one exists."""
    problem = frame(member.account, member.request, team, LEAVING_TRIES, taken)
    tried: list[Build] = []

    while len(tried) < LEAVING_TRIES:
        build = best_build(problem, member.request, tried)
        if build is None:
            break

        worn = taken | {a.id for a in build.artifacts}
        if not rest or feasible(rest, team, worn):
            return build

        tried.append(build)

    return best_together(member, rest, team, taken)


def best_together(
    member: Member, rest: Sequence[Member], team: frozenset[int], taken: frozenset[int]
) -> Build:
    """The member's best build with the rest meeting their limits, all in one model."""
    together = [member, *rest]
    problems = [frame(m.account, m.request, team, len(together), taken) for m in together]
    milps = formulate(problems, [m.request.set_minimums for m in together])

    for milp, other in zip(milps, together, strict=True):
        add_limits(milp, other.request)

    if (build := maximise_ranking(milps[0], problems[0], member.request)) is None:
        raise AssertionError("the rest was feasible with the member before")

    return build


def why_unmet(members: Sequence[Member], team: frozenset[int]) -> Unmet | Clash:
    """Who can't meet their limits even alone, and how close they get; none: a clash."""
    reasons: list[SetsRuleOut | Shortfall | None] = []

    for member in members:
        problem = frame(member.account, member.request, team, 1)

        if reason := check_sets(problem, member.request):
            reasons.append(SetsRuleOut(reason))
        elif best_build(problem, member.request, []) is None:
            reasons.append(explain_shortfall(problem, member.request))
        else:
            reasons.append(None)

    return Unmet(tuple(reasons)) if any(reasons) else Clash()


def frame(
    account: Account,
    request: Request,
    team: frozenset[int],
    keep: int,
    taken: frozenset[int] = frozenset(),
) -> Problem:
    """`team`: champions whose gear counts as the champion's own; `keep`: see `prune`;
    `taken`: pieces gone to someone else."""
    champion = request.champion
    tables = account.tables
    base = base_stats(champion, tables)
    battle = request.battle.bonuses()
    wearing = [
        a for a in account.artifacts if a.id not in taken and wearable(a, account, request, team)
    ]
    piece_stats = {a.id: artifact_stats(a, base) for a in wearing}
    pieces = prune(wearing, piece_stats, request, keep)

    return Problem(
        champion=champion,
        tables=tables,
        base=base,
        battle=battle,
        constant=constant_stats(champion, tables, battle),
        pieces=pieces,
        piece_stats={a.id: piece_stats[a.id] for a in pieces},
        sets={a.set_id: tables.sets[a.set_id] for a in pieces if a.set_id in tables.sets},
        set_multiplier=set_multiplier(champion, tables),
    )


def wearable(artifact: Artifact, account: Account, request: Request, team: frozenset[int]) -> bool:
    if artifact.faction not in (None, request.champion.faction):
        return False

    if not slot_unlocked(request.champion, artifact.slot, account.tables.gear):
        return False

    if artifact.level <= request.above_level:
        return False

    if (owner := account.owners.get(artifact.id)) in team:
        return True

    return request.gear.allows(artifact.id, owner)


def prune(
    pieces: list[Artifact], piece_stats: dict[int, Stats], request: Request, keep: int
) -> tuple[Artifact, ...]:
    """Drop pieces that at least `keep` others in the same slot, set and faction lock match
    or beat on every stat the request uses: swapping a free one of those in never makes a
    build worse, so the best builds never need it. With b builds and n champions, b + n - 1
    leaves one free: teammates wear at most n - 1 of them, earlier builds rule out b - 1."""
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

            if beaten_by < keep:
                kept.append(artifact)

    return tuple(kept)


def directions(request: Request) -> dict[Stat, int]:
    """Each stat the request uses: +1 more is better, -1 less is better, 0 must match."""
    wanted: dict[Stat, int] = {stat: 1 for stat in request.minimums}

    for goal in request.ranking:
        match goal:
            case DamageGoal(formula=formula):
                wanted |= {stat: 1 for stat in formula.coefficients} | {Stat.CD: 1}

            case Lands() | Resists() as rate:
                wanted[rate.stat] = 1

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
    (milp,) = formulate([problem], [request.set_minimums])
    add_limits(milp, request)

    for build in excluded:
        milp.highs.addConstr(
            milp.highs.qsum(milp.chosen[a.id] for a in build.artifacts) <= len(build.artifacts) - 1
        )

    return maximise_ranking(milp, problem, request)


def maximise_ranking(milp: "Milp", problem: Problem, request: Request) -> Build | None:
    """The request's goals maximised in order, each held within the slack of its best; None
    if the model has no solution."""
    for goal in request.ranking:
        objective = ranked(milp, goal, problem)

        if (best := maximise(milp, objective.expression)) is None:
            return None

        hold(milp, objective, best, request.slack)

    return solved_build(milp, problem)


def solved_build(milp: "Milp", problem: Problem) -> Build:
    """The member's pieces in the model's solution."""
    picked = tuple(a for a in problem.pieces if milp.highs.val(milp.chosen[a.id]) > 0.5)
    return Build(picked, build_stats(problem.champion, picked, problem.tables, problem.battle))


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
    (milp,) = formulate([problem], [request.set_minimums])
    best = maximise(milp, way * milp.stats[stat])
    return None if best is None else way * best


type Expression = highspy.highs_linear_expression | highspy.highs_var


@dataclass(frozen=True)
class Milp:
    """A champion in a HiGHS model (shared by a team's members): a binary per piece, and each
    stat as an expression of them."""

    highs: highspy.Highs
    chosen: dict[int, highspy.highs_var]  # artifact id -> 1 if worn
    stats: dict[Stat, highspy.highs_linear_expression]
    ignore: list[ActiveIgnore[Expression]]
    damage: list[ActiveBonus[Expression]]


@dataclass(frozen=True)
class SetTerms:
    """What a set adds to the model: to each stat, and the ignore-DEF passives and damage
    bonuses it turns on."""

    stats: Sequence[tuple[Stat, Expression]]
    ignore: Sequence[ActiveIgnore[Expression]]
    damage: Sequence[ActiveBonus[Expression]]


def formulate(problems: Sequence[Problem], set_minimums: Sequence[dict[int, int]]) -> list[Milp]:
    """One model, a member per problem; no piece worn twice."""
    highs = highspy.Highs()
    highs.silent()
    highs.cbMipInterrupt += interrupt
    milps = [
        add_member(highs, problem, minimums)
        for problem, minimums in zip(problems, set_minimums, strict=True)
    ]
    wearers: dict[int, list[highspy.highs_var]] = {}

    for milp in milps:
        for artifact_id, chosen in milp.chosen.items():
            wearers.setdefault(artifact_id, []).append(chosen)

    for shared in wearers.values():
        if len(shared) > 1:
            highs.addConstr(highs.qsum(shared) <= 1)

    return milps


def add_member(highs: highspy.Highs, problem: Problem, set_minimums: dict[int, int]) -> Milp:
    """A champion's pieces, sets and stats, added to the model."""
    chosen = {a.id: highs.addBinary() for a in problem.pieces}
    terms: dict[Stat, list] = {stat: [] for stat in Stat}
    ignore: list[ActiveIgnore[Expression]] = []
    damage: list[ActiveBonus[Expression]] = []

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
        damage += added.damage

        for stat, term in added.stats:
            terms[stat].append(term)

    stats = {stat: highs.qsum(terms[stat]) + problem.constant[stat] for stat in Stat}
    return Milp(highs, chosen, stats, ignore, damage)


def set_terms(
    highs: highspy.Highs, artifact_set: ArtifactSet, count: Expression, problem: Problem
) -> SetTerms:
    """What the set adds, given the expression counting its pieces. Piece-count variables are
    tied to `count` exactly, so a stat maximum can't hide a bonus."""
    base, multiplier = problem.base, problem.set_multiplier

    match artifact_set:
        case FixedSet(pieces=pieces, ignore=ignore, damage=damage):
            per_set = set_stats(artifact_set, pieces, base, multiplier)
            if not any(per_set.values()) and not ignore and not damage:
                return SetTerms([], [], [])

            times = highs.addIntegral(lb=0, ub=MAX_PIECES // pieces)
            highs.addConstr(pieces * times <= count)
            highs.addConstr(pieces * times >= count - (pieces - 1))
            stat_terms = [(stat, amount * times) for stat, amount in per_set.items() if amount]
            return SetTerms(
                stat_terms,
                [ActiveIgnore(source, times) for source in ignore],
                [ActiveBonus(source, times) for source in damage],
            )

        case VariableSet(ignore_at=ignore_at, damage_at=damage_at):
            totals = {
                pieces: set_stats(artifact_set, pieces, base, multiplier)
                for pieces in range(1, MAX_PIECES + 1)
            }
            if (
                not any(any(t.values()) for t in totals.values())
                and not any(ignore_at.values())
                and not any(damage_at.values())
            ):
                return SetTerms([], [], [])

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
            damage_terms: list[ActiveBonus[Expression]] = [
                ActiveBonus(source, exactly[pieces])
                for pieces in range(1, MAX_PIECES + 1)
                if (reached := [tier for tier in damage_at if tier <= pieces])
                for source in damage_at[max(reached)]
            ]
            return SetTerms(stat_terms, ignore_terms, damage_terms)


def add_limits(milp: Milp, request: Request) -> None:
    for stat, minimum in request.minimums.items():
        milp.highs.addConstr(milp.stats[stat] >= minimum)

    for stat, maximum in request.maximums.items():
        milp.highs.addConstr(milp.stats[stat] <= maximum)


@dataclass(frozen=True)
class Ranked:
    """A goal as the solver maximises it (damage's log; a capped stat's value up to its cap)."""

    expression: Expression
    goal: Goal


def ranked(milp: Milp, goal: Goal, problem: Problem) -> Ranked:
    match goal:
        case DamageGoal():
            return Ranked(log_damage(milp, goal, problem), goal)

        case Lands() | Resists() as rate:
            return Ranked(capped(milp, rate.stat, rate.most_useful()), goal)

        case stat if (cap := RANK_CAPS.get(stat)) is not None:
            return Ranked(capped(milp, stat, cap), goal)

        case stat:
            return Ranked(milp.stats[stat], goal)


def capped(milp: Milp, stat: Stat, cap: float) -> highspy.highs_var:
    """The stat, counted up to `cap`: more is wasted past it."""
    value = milp.highs.addVariable(lb=-highspy.kHighsInf, ub=cap)
    milp.highs.addConstr(value <= milp.stats[stat])
    return value


def hold(milp: Milp, objective: Ranked, best: float, slack: float) -> None:
    """Keep the goal within `slack` of its best while later goals are maximised."""
    milp.highs.addConstr(objective.expression >= held_floor(objective.goal, best, slack))


def held_floor(goal: Goal, best: float, slack: float) -> float:
    """The least the ranked expression may fall to: damage within `slack` of its best (it's
    ranked by its log), a rate within `slack` of its best rate, a stat of its best stat."""
    match goal:
        case DamageGoal():
            return best + math.log(1 - slack)

        case Lands() | Resists() as rate:
            least = rate.least_for(rate.rate(best) * (1 - slack))
            return best if least is None else min(least, best)

        case _:
            return best - slack * abs(best)


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
    log_bonus = log_damage_bonus(milp)
    return log_formula + log_crit + log_bonus + log_defence_multiplier(milp, goal, problem)


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
    it up to the curve (log is concave, so tangents lie above it). The expression (a term
    per piece) gets a variable of its own, so each tangent row holds two entries rather than
    one per piece: the dense rows made every LP iteration several times slower."""
    value = highs.addVariable(lb=-highspy.kHighsInf)
    highs.addConstr(value == expression)
    log = highs.addVariable(lb=-highspy.kHighsInf)

    for point in points:
        highs.addConstr(log <= math.log(point) + (value - point) / point)

    return log


def log_damage_bonus(milp: Milp):
    """log(1 + the sets' damage bonus), exact: log is concave, so tangents at every total the
    sets can reach hold it to the curve at each of them. Bonuses granted by several sets count
    once unless they stack per set, and then up to their cap."""
    highs = milp.highs
    by_skill: dict[int, list[ActiveBonus[Expression]]] = {}

    for bonus in milp.damage:
        by_skill.setdefault(bonus.source.skill_id, []).append(bonus)

    if not by_skill:
        return 0

    parts = []
    reachable = {0.0}

    for group in by_skill.values():
        source = group[0].source
        active = highs.qsum(bonus.times for bonus in group)

        if source.per_set:
            cap = highspy.kHighsInf if source.cap is None else source.cap
            part = highs.addVariable(lb=0, ub=cap)
            highs.addConstr(part <= source.value * active)
            values = {min(source.value * times, cap) for times in range(MAX_PIECES + 1)}
        else:
            once = highs.addBinary()
            highs.addConstr(once <= active)
            part = source.value * once
            values = {0.0, source.value}

        parts.append(part)
        reachable = {total + value for total in reachable for value in values}

    return log_under_tangents(highs, 1 + highs.qsum(parts), sorted(1 + v for v in reachable))


def log_defence_multiplier(milp: Milp, goal: DamageGoal, problem: Problem):
    """log(DEF multiplier), exact: the sets' ignore DEF is a multiple of IGNORE_STEP, so a
    binary per step carries its exact value. The steps stop at the most any build ignores:
    the term is convex, so the LP relaxation takes the chord from step 0 to the top one, and
    a top past what's reachable (every source at once reaches DEF multiplier 1) made that
    bound loose enough to double the solve."""
    highs = milp.highs
    top = most_ignore(problem, goal)
    steps = range(round(top / IGNORE_STEP) + 1)
    at_step = [highs.addBinary() for _ in steps]
    highs.addConstr(highs.qsum(at_step) == 1)
    # At most what the sets give: the term rises with ignore DEF, so maximising takes the
    # highest step allowed, and step 0 is always feasible (an equality makes HiGHS struggle
    # to find a first solution).
    highs.addConstr(
        highs.qsum(IGNORE_STEP * step * at for step, at in zip(steps, at_step, strict=True))
        <= ignore_total(milp, goal)
    )
    return highs.qsum(
        math.log(defence_multiplier(goal.enemy_defence, goal.skill_ignore + IGNORE_STEP * step))
        * at
        for step, at in zip(steps, at_step, strict=True)
    )


def most_ignore(problem: Problem, goal: DamageGoal) -> float:
    """The most DEF the sets of any one build ignore for the goal's skill."""
    (milp,) = formulate([problem], [{}])

    if not any(applies(goal, passive.source) for passive in milp.ignore):
        return 0.0

    return maximise(milp, ignore_total(milp, goal)) or 0.0


def ignore_total(milp: Milp, goal: DamageGoal) -> Expression:
    """The DEF the chosen sets ignore for the goal's skill. Passives granted by several sets
    count once unless they stack per set."""
    highs = milp.highs
    by_skill: dict[int, list[ActiveIgnore[Expression]]] = {}

    for passive in milp.ignore:
        if applies(goal, passive.source):
            by_skill.setdefault(passive.source.skill_id, []).append(passive)

    parts = []

    for group in by_skill.values():
        source = group[0].source
        active = highs.qsum(passive.times for passive in group)

        if abs(source.value / IGNORE_STEP - round(source.value / IGNORE_STEP)) > 1e-9:
            raise ValueError(f"ignore DEF {source.value} isn't a multiple of {IGNORE_STEP}")

        if source.per_set:
            parts.append(source.value * active)
        else:
            once = highs.addBinary()
            highs.addConstr(once <= active)
            parts.append(source.value * once)

    return highs.qsum(parts)


def maximise(milp: Milp, goal) -> float | None:
    """The best value of `goal`, leaving its solution in the model; None if infeasible."""
    milp.highs.maximize(goal)
    check_stopped()

    if milp.highs.getModelStatus() != highspy.HighsModelStatus.kOptimal:
        return None

    return milp.highs.val(goal)


def stop() -> None:
    """Stops the solve running (if any): see the module's docstring."""
    STOPPING.set()


class Interrupted(Exception):
    """A HiGHS solve was stopped: unwinds a workflow's steps, with the builds found so far."""

    def __init__(self, builds: Sequence[Build] = ()):
        super().__init__("stopped")
        self.builds = list(builds)


def interrupt(event) -> None:
    """HiGHS's MIP interrupt callback: stop once `stop` was called."""
    if STOPPING.is_set():
        event.interrupt()


def check_stopped() -> None:
    """After a HiGHS solve: raise `Interrupted` if it (or the workflow) was stopped."""
    if STOPPING.is_set():
        raise Interrupted()
