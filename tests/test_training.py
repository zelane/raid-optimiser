"""
test_training.py - brewing champions for an event scoring level-ups.

- `test_xp_carries_over`: a brew's XP takes a champion up as many levels as it covers
- `test_half_level_on_own_affinity`: the game's tables give 2, 4 and 7 brews for 3★, 4★ and 5★
"""

import pytest

from optimiser.events import Condition, Rule
from optimiser.levelling import Levelling, level_after, load_levelling
from optimiser.paths import GAME
from webui.service.training import brew_row

TRAINING = tuple(
    Rule("Hero_LevelUp", (Condition("Hero", "Grade", grade),), points)
    for grade, points in [("Stars3", 2), ("Stars4", 3), ("Stars5", 6)]
)


def test_xp_carries_over() -> None:
    levelling = Levelling({"Stars3": (10, 20, 30)}, brew=20, matching=30)

    assert level_after(levelling, "Stars3", 29) == 2
    assert level_after(levelling, "Stars3", 30) == 3
    assert level_after(levelling, "Stars3", 999) == 4  # the top level


@pytest.mark.skipif(not GAME.joinpath("levelling.json").exists(), reason="needs just static")
def test_half_level_on_own_affinity() -> None:
    levelling = load_levelling(GAME)
    rows = [brew_row(TRAINING, grade, levelling) for grade in ("Stars3", "Stars4", "Stars5")]

    assert [(row.brews, row.level) for row in rows if row] == [(2, 15), (4, 21), (7, 26)]
    assert [row.points for row in rows if row] == [28, 60, 150]
