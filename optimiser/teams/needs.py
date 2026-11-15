"""
needs.py - what a team must bring (`Goals`): objectives, each needs met against a `Target` and
maybe waiting on another objective met first, and extras every team must bring besides. A need
is one of several tags (`AnyOf`), so many different buffs or debuffs (`Distinct`; debuffs the
target isn't immune to), or one met for any team by what it can wear (`Given`). Counts of
debuff instances count Poisons as many as there are: each champion's most from one skill (two
Poisons at once), and one for gear any champion can wear that places one (the Toxic set).
Where Poisons pile up over the fight (`Distinct.accumulates`: the Chimera, which gets several
of the team's turns to each of its own), any Poison source meets the count, given speed.

- `AnyOf`, `Distinct`, `Given`, `Need`, `Requirement`, `Objective`, `Goals`: what a team
  must bring
- `STACKING`, `stacking_tags`, `counts_toward`, `kinds_toward`, `instances`, `stacked`: what
  counts toward a need
"""

from dataclasses import dataclass

from optimiser.teams.kits import Kit
from optimiser.teams.tags import Side, Tag, Target

# Status effects whose instances stack (Poisons): a team placing one can pile up a debuff
# count on its own, if it's fast enough (or extends them).
STACKING = frozenset({"ContinuousDamage"})


@dataclass(frozen=True)
class AnyOf:
    """At least one of these on the team."""

    tags: frozenset[Tag]


@dataclass(frozen=True)
class Distinct:
    """At least `count` status effects of a side (debuffs the target isn't immune to, or
    buffs), `excluded` not counting. Different ones, unless `instances`: the rule counts every
    debuff on the target, so Poisons (they stack) count as many as a team places (`stacked`),
    and `gear` (its name and `Rating` score), worn by any champion, places one more; or,
    when they `accumulate` over the fight, any Poison meets it."""

    side: Side
    count: int
    instances: bool = False
    excluded: frozenset[str] = frozenset()
    gear: tuple[str, float] | None = None
    accumulates: bool = False


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
    """A need, and the target it's met against."""

    need: Need
    target: Target


@dataclass(frozen=True)
class Objective:
    """Something the team is after (a Chimera trial): its needs, met against `target`, and
    `requires`: the objective that must be met first (its `key`), if any."""

    key: int
    target: Target
    needs: tuple[Need, ...]
    requires: int | None = None


@dataclass(frozen=True)
class Goals:
    """What a team of at most `size` is after: the objectives (in order: one waiting on
    another comes after it), and `extras`: debuffs, buffs and effects wanted besides (one of
    some, or so many different), in every team the search offers, met against
    `extras_target`."""

    objectives: tuple[Objective, ...]
    extras: tuple[AnyOf | Distinct, ...]
    extras_target: Target
    size: int

    def objective_requirements(self, objective: Objective) -> list[Requirement]:
        return [Requirement(need, objective.target) for need in objective.needs]

    @property
    def extra_requirements(self) -> list[Requirement]:
        return [Requirement(extra, self.extras_target) for extra in self.extras]

    @property
    def requirements(self) -> list[Requirement]:
        """Every objective's, then the extras'."""
        objectives = [r for o in self.objectives for r in self.objective_requirements(o)]
        return objectives + self.extra_requirements


def counts_toward(tag: Tag, need: Distinct, target: Target) -> bool:
    """Whether the tag is one of the effects the need counts."""
    if tag.side != need.side or tag.name in need.excluded:
        return False

    return tag.side != Side.DEBUFF or tag.name not in target.immune


def stacking_tags(need: Distinct) -> frozenset[Tag]:
    return frozenset(Tag(need.side, name) for name in STACKING)


def kinds_toward(need: Distinct, tags: frozenset[Tag], target: Target) -> frozenset[Tag]:
    """The different effects among `tags` the need counts (for instances, those that don't
    stack: `stacked` counts those)."""
    counted = frozenset(t for t in tags if counts_toward(t, need, target))
    return counted - stacking_tags(need) if need.instances else counted


def stacked(need: Distinct, kit_tags: frozenset[Tag], counts: dict[Tag, int]) -> int:
    """The instances of stacking effects one champion places toward the need: the most one of
    its skills places (`Kit.counts`)."""
    if not need.instances:
        return 0

    return sum(counts.get(t, 1) for t in stacking_tags(need) & kit_tags)


def instances(need: Distinct, kits: list[Kit], target: Target) -> int:
    """How many the team brings toward the need: its different effects, its Poisons, and
    the gear's."""
    tags = frozenset().union(*(kit.tags for kit in kits))
    poisons = sum(stacked(need, kit.tags, kit.counts) for kit in kits)
    return len(kinds_toward(need, tags, target)) + poisons + (1 if need.gear else 0)
