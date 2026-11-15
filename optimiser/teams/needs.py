"""
needs.py - what a team must bring (`Goals`): objectives, each needs met against a `Target` and
maybe waiting on another objective met first, and extras every team must bring besides. A need
is one of several tags (`AnyOf`), so many different buffs or debuffs (`Distinct`; debuffs the
target isn't immune to), or one met for any team by what it can wear (`Given`). Counts of
debuff instances count Poisons: they stack, so a team placing them can reach the count if it's
fast enough.

- `AnyOf`, `Distinct`, `Given`, `Need`, `Requirement`, `Objective`, `Goals`: what a team
  must bring
- `STACKING`, `stacking_tags`, `counts_toward`: what counts toward a need
"""

from dataclasses import dataclass

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
    debuff on the target, so a team placing Poisons (they stack) meets it too."""

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
