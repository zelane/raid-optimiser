"""
test_info.py - the info page's Faction Wars section: which battle quests a stage may still
need from its star count, and the quests' texts.

- `test_stage_rows_from_star_counts`: unfought, unbeaten, one short (one of two), complete
- `test_quest_text_fills_in_its_parameter`: counts as they are, fractions as percentages
"""

from optimiser.account import StageProgress
from optimiser.enemies import quest_text
from webui.service.info import stage_row

QUESTS = ("Beat Stage", "5 Champions, no losses", "Defeat 3+ enemies under 7+ debuffs")


def test_stage_rows_from_star_counts() -> None:
    unfought = stage_row(20, QUESTS, None)
    assert unfought is not None and unfought.open == QUESTS and not unfought.one_of

    unbeaten = stage_row(21, QUESTS, StageProgress(passed=False, stars=0))
    assert unbeaten is not None and unbeaten.state == "not beaten"

    one_short = stage_row(19, QUESTS, StageProgress(passed=True, stars=2))
    assert one_short is not None and one_short.open == QUESTS[1:] and one_short.one_of

    two_short = stage_row(15, QUESTS, StageProgress(passed=True, stars=1))
    assert two_short is not None and two_short.open == QUESTS[1:] and not two_short.one_of

    assert stage_row(18, QUESTS, StageProgress(passed=True, stars=3)) is None


def test_quest_text_fills_in_its_parameter() -> None:
    assert quest_text("Defeat {0}+ enemies", 3.0) == "Defeat 3+ enemies"
    assert quest_text("Keep all your Champion's HP above {0}%", 0.5) == (
        "Keep all your Champion's HP above 50%"
    )
    assert quest_text("Clear the Stage in {0} turns", 200.0) == "Clear the Stage in 200 turns"
