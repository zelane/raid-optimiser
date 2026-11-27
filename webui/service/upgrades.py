"""
upgrades.py - the pieces to upgrade for an event scoring gear upgrades (Gear Enhancement): the
usual way is to take new 5★ and 6★ pieces from +0 to +12, and the plan says what one of each
earns that way (the event's points for each level reached on the way), so the page can say how
many reaching a milestone takes, all of one rank: enough without overshooting.

- `TO_LEVEL`, `RANKS`: how far and which ranks
- `UpgradeRow`, `UpgradePlan`: the views
- `upgrade_plan`: an event's plan, if it scores upgrades
- `upgrade_points`: what one piece earns
"""

from dataclasses import dataclass
from typing import Literal

from optimiser.events import GameEvent, Rule, rule_points

UPGRADE = "Artifact_Upgrade"
TO_LEVEL = 12
RANKS = {"Five": 5, "Six": 6}  # the game's rank -> stars


@dataclass(frozen=True)
class UpgradeRow:
    stars: int
    points: int  # one piece taken from +0 to `UpgradePlan.level`


@dataclass(frozen=True)
class UpgradePlan:
    level: int
    rows: tuple[UpgradeRow, ...]
    kind: Literal["upgrades"] = "upgrades"


def upgrade_plan(event: GameEvent) -> UpgradePlan | None:
    rows = tuple(
        UpgradeRow(stars, points)
        for rank, stars in RANKS.items()
        if (points := upgrade_points(event.rules, rank, TO_LEVEL))
    )
    return UpgradePlan(TO_LEVEL, rows) if rows else None


def upgrade_points(rules: tuple[Rule, ...], rank: str, to_level: int) -> int:
    """What a piece of this rank earns going from +0 to `to_level`: what each level reached on
    the way earns (a rule held to anything else, its rarity or set, is left out)."""
    return sum(
        rule_points(rules, UPGRADE, {"Rank": rank, "Level": level})
        for level in range(1, to_level + 1)
    )
