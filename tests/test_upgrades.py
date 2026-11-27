"""
test_upgrades.py - upgrading gear for an event scoring upgrades.

- `test_points_to_plus_twelve`: each level's points up to +12 for the piece's rank, no further
"""

from optimiser.events import Condition, Rule
from webui.service.upgrades import upgrade_points

ENHANCEMENT = tuple(
    Rule(
        "Artifact_Upgrade",
        (Condition("Artifact", "Rank", rank), Condition("Artifact", "Level", level)),
        points,
    )
    for rank, by_level in [("Five", {4: 2, 8: 5, 12: 40, 16: 270}), ("Six", {4: 3, 8: 10, 12: 65})]
    for level, points in by_level.items()
)


def test_points_to_plus_twelve() -> None:
    assert upgrade_points(ENHANCEMENT, "Five", 12) == 47
    assert upgrade_points(ENHANCEMENT, "Six", 12) == 78
    assert upgrade_points(ENHANCEMENT, "Four", 12) == 0
