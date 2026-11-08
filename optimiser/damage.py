"""
damage.py - a skill's crit-hit damage against a target's DEF, as the game computes it
(`DamageCalculator`, read from the game code): the skill's multiplier formula
× (1 + book bonuses) × (1 + C.DMG) × the DEF multiplier, 1 - 0.85 (1 - e^(-effDEF / 1500)),
where effDEF = DEF × (1 - ignored). Ignored DEF is the skill's own plus the sets' passives;
they add.

Left out, as gear doesn't change them: buffs and debuffs, affinity, the random roll, and the
dealt-damage substats (PvP, boss, dungeon).

- `DEF_REDUCTION_CAP`, `DEF_SCALE`, `STAT_NAMES`: the game's constants, and formula names
- `LinearFormula`, `DamageGoal`, `Unsupported`: what's ranked, or why a skill can't be
- `ActiveIgnore`: a set's ignore-DEF passive, as worn
- `damage_goal`: a champion's skill and a target's DEF into a goal (the boundary)
- `estimate_damage`, `ignored_by_sets`, `ignore_sources`, `applies`, `defence_multiplier`:
  the model
- `parse_formula`, `linearise`: formula text to a linear function of stats
"""

import ast
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from optimiser.account import (
    Artifact,
    ArtifactSet,
    Champion,
    FixedSet,
    IgnoreDefence,
    Skill,
    Stat,
    Stats,
    VariableSet,
)

DEF_REDUCTION_CAP = 0.85  # DEF can cut damage by at most 85 %
DEF_SCALE = 1500  # effective DEF at which ~63 % of that cap applies

# The champion's own stats as skill formulas name them.
STAT_NAMES = {
    "ATK": Stat.ATK,
    "DEF": Stat.DEF,
    "HP": Stat.HP,
    "SPD": Stat.SPD,
    "RES": Stat.RES,
    "ACC": Stat.ACC,
}


@dataclass(frozen=True)
class LinearFormula:
    """constant + Σ coefficient × stat."""

    coefficients: dict[Stat, float]
    constant: float = 0

    def value(self, stats: Stats) -> float:
        return self.constant + sum(k * stats[stat] for stat, k in self.coefficients.items())

    def scaled(self, factor: float) -> "LinearFormula":
        return LinearFormula(
            {stat: k * factor for stat, k in self.coefficients.items()}, self.constant * factor
        )

    def plus(self, other: "LinearFormula") -> "LinearFormula":
        stats = self.coefficients.keys() | other.coefficients.keys()
        return LinearFormula(
            {s: self.coefficients.get(s, 0) + other.coefficients.get(s, 0) for s in stats},
            self.constant + other.constant,
        )


@dataclass(frozen=True)
class DamageGoal:
    """Crit-hit damage of one skill (all its unconditional hits) against `enemy_defence`."""

    skill_name: str
    formula: LinearFormula
    skill_ignore: float  # the skill's own ignore DEF (0.15 ignores 15 %)
    aoe: bool
    book_bonus: float  # from the champion's books in this skill
    enemy_defence: float


@dataclass(frozen=True)
class Unsupported:
    reason: str


@dataclass(frozen=True)
class ActiveIgnore[T]:
    """A set's ignore-DEF passive and how many times it's active: a count, or the solver's
    expression for one."""

    source: IgnoreDefence
    times: T


def damage_goal(skill: Skill, champion: Champion, enemy_defence: float) -> DamageGoal | Unsupported:
    """The goal for `skill`, if its damage depends only on the champion's own stats."""
    if not skill.hits:
        return Unsupported("no direct damage")

    total = LinearFormula({})

    for hit in skill.hits:
        if (formula := parse_formula(hit.formula)) is None:
            return Unsupported(f"{hit.formula} depends on more than the champion's stats")

        total = total.plus(formula.scaled(hit.count))

    if len({hit.defence_modifier for hit in skill.hits}) > 1:
        return Unsupported("its hits ignore different amounts of DEF")

    level = champion.skill_levels.get(skill.id, 1)
    return DamageGoal(
        skill_name=skill.name,
        formula=total,
        skill_ignore=-skill.hits[0].defence_modifier,
        aoe=skill.aoe,
        book_bonus=sum(skill.book_damage[: level - 1]),
        enemy_defence=enemy_defence,
    )


def estimate_damage(
    goal: DamageGoal, stats: Stats, artifacts: Iterable[Artifact], sets: dict[int, ArtifactSet]
) -> float:
    """The skill's crit-hit damage with these stats, wearing these artifacts."""
    ignored = goal.skill_ignore + ignored_by_sets(goal, artifacts, sets)
    return (
        goal.formula.value(stats)
        * (1 + goal.book_bonus)
        * (1 + stats[Stat.CD])
        * defence_multiplier(goal.enemy_defence, ignored)
    )


def ignored_by_sets(
    goal: DamageGoal, artifacts: Iterable[Artifact], sets: dict[int, ArtifactSet]
) -> float:
    """The DEF the worn sets' passives ignore for this skill."""
    pieces = Counter(a.set_id for a in artifacts)
    active = [
        passive
        for set_id, count in pieces.items()
        if set_id in sets
        for passive in ignore_sources(sets[set_id], count)
        if applies(goal, passive.source)
    ]
    per_skill: dict[int, float] = {}

    for passive in active:
        source = passive.source

        if source.per_set:
            per_skill[source.skill_id] = (
                per_skill.get(source.skill_id, 0) + source.value * passive.times
            )
        else:
            per_skill[source.skill_id] = source.value  # the same passive twice counts once

    return sum(per_skill.values())


def ignore_sources(artifact_set: ArtifactSet, count: int) -> list[ActiveIgnore[int]]:
    """The set's ignore-DEF passives active with `count` pieces."""
    match artifact_set:
        case FixedSet(pieces=pieces, ignore=ignore):
            times = count // pieces
            return [ActiveIgnore(source, times) for source in ignore] if times else []

        case VariableSet(ignore_at=ignore_at):
            reached = [pieces for pieces in ignore_at if pieces <= count]
            return (
                [ActiveIgnore(source, 1) for source in ignore_at[max(reached)]] if reached else []
            )


def applies(goal: DamageGoal, source: IgnoreDefence) -> bool:
    """AoE-only passives help AoE skills only."""
    return goal.aoe or not source.aoe_only


def defence_multiplier(enemy_defence: float, ignored: float) -> float:
    """The share of damage that gets through `enemy_defence` with `ignored` of it ignored."""
    effective = enemy_defence * max(0.0, 1 - ignored)
    return 1 - DEF_REDUCTION_CAP * (1 - math.exp(-effective / DEF_SCALE))


def parse_formula(text: str) -> LinearFormula | None:
    """The formula as a linear function of the champion's stats; None if it isn't one
    (it uses the target's stats, battle state, or multiplies stats together)."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError:
        return None

    return linearise(tree.body)


def linearise(node: ast.expr) -> LinearFormula | None:
    match node:
        case ast.Constant(value=int() | float() as number) if not isinstance(number, bool):
            return LinearFormula({}, float(number))

        case ast.Name(id=name) if name in STAT_NAMES:
            return LinearFormula({STAT_NAMES[name]: 1.0})

        case ast.UnaryOp(op=ast.USub(), operand=operand):
            inner = linearise(operand)
            return inner.scaled(-1) if inner else None

        case ast.BinOp(left=left, op=ast.Add() | ast.Sub() as op, right=right):
            if (lhs := linearise(left)) is None or (rhs := linearise(right)) is None:
                return None

            return lhs.plus(rhs if isinstance(op, ast.Add) else rhs.scaled(-1))

        case ast.BinOp(left=left, op=ast.Mult(), right=right):
            if (lhs := linearise(left)) is None or (rhs := linearise(right)) is None:
                return None

            if not lhs.coefficients:
                return rhs.scaled(lhs.constant)

            if not rhs.coefficients:
                return lhs.scaled(rhs.constant)

            return None  # stat × stat

        case ast.BinOp(left=left, op=ast.Div(), right=right):
            if (lhs := linearise(left)) is None or (rhs := linearise(right)) is None:
                return None

            if rhs.coefficients or rhs.constant == 0:
                return None

            return lhs.scaled(1 / rhs.constant)

        case _:
            return None
