"""
training.py - the brews to use for an event scoring level-ups (Champion Training): the usual
way is to brew new 3★, 4★ and 5★ champions to half their top level (15, 20, 25) with brews of
their own affinity, and the plan says what one champion of each grade earns that way, so the
page can say how many reaching a milestone takes (all of one grade).

Each level gained scores the grade's level-up points. A brew of another affinity gives two
thirds as much XP (`Levelling.brew`), so takes about half as many brews again.

- `GRADES`: the grades brewed
- `BrewRow`, `BrewPlan`: the views
- `brew_plan`: an event's plan, if it scores level-ups
- `brew_row`: one grade's
"""

from dataclasses import dataclass
from typing import Literal

from optimiser.events import GameEvent, Rule, rule_points
from optimiser.levelling import Levelling, brews_to_level, level_after

GRADES = ("Stars3", "Stars4", "Stars5")
LEVEL_UP = "Hero_LevelUp"


@dataclass(frozen=True)
class BrewRow:
    """A champion of `stars` brewed from level 1 to half its top level: `brews` of its own
    affinity, `level` the level they take it to, `points` what that earns, `per_brew` each
    brew's share."""

    stars: int
    brews: int
    level: int
    points: int
    per_brew: float


@dataclass(frozen=True)
class BrewPlan:
    rows: tuple[BrewRow, ...]
    brew: int  # XP a brew gives: `matching` on a champion of its own affinity
    matching: int
    kind: Literal["brews"] = "brews"


def brew_plan(event: GameEvent, levelling: Levelling) -> BrewPlan | None:
    rows = tuple(row for grade in GRADES if (row := brew_row(event.rules, grade, levelling)))
    return BrewPlan(rows, levelling.brew, levelling.matching) if rows else None


def brew_row(rules: tuple[Rule, ...], grade: str, levelling: Levelling) -> BrewRow | None:
    if not (per_level := rule_points(rules, LEVEL_UP, {"Grade": grade})):
        return None

    half = levelling.max_level(grade) // 2
    brews = brews_to_level(levelling, grade, half, levelling.matching)
    level = level_after(levelling, grade, brews * levelling.matching)
    points = (level - 1) * per_level
    return BrewRow(int(grade.removeprefix("Stars")), brews, level, points, round(points / brews, 1))
