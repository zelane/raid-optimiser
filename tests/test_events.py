"""
test_events.py - events: the game's JSON decoded by its schema, the account's bracket, and the
points tables the page draws.

- `test_decode_names_keys_enums_and_text`: short keys, enums by number, a text key's default
- `test_texts_from_settings_ids`: title and points' name by id, none without settings
- `test_tournament_ends_with_its_bracket`: start + bracket, a day past its stored end
- `test_rule_conditions_and_turn_points`: a rule's set fields, a turn-scored fight's range
- `test_events_not_loaded_yet`: a file read while the game was loading holds no events
- `test_rules_add_where_they_hold`: values, any-of, stage ranges; an unknown fact fails
- `test_turn_points_match_real_fights`: Sand Devil 25 as fought: 44 turns 43 points, 22 turns 48
- `test_bracket_from_standing_else_levels`: the standing's bracket, else the levels' one
- `test_points_grid_when_rules_vary_along_two`: rank × level, zero rows dropped
- `test_points_rows_share_what_every_rule_sets`: the dungeon said once, stages as one field
"""

from datetime import UTC, datetime

from optimiser.events import (
    Bracket,
    Condition,
    Events,
    EventTexts,
    GameEvent,
    Milestone,
    Rule,
    Standing,
    TurnPoints,
    account_levels,
    bracket_for,
    decode,
    event_end,
    holds,
    load_events,
    milestones_for,
    parse_rule,
    parse_texts,
    rule_points,
)
from webui.service.events import Names, points_tables

SCHEMA = {
    "classes": {
        "Quest": {
            "i": {"name": "PrototypeId", "type": "int"},
            "c": {"name": "CategoryId", "type": "QuestCategoryId"},
            "n": {"name": "Name", "type": "SharedLTextKey"},
            "r": {"name": "Rules", "type": "Dictionary<GlobalEventAction, List<int>>"},
        }
    },
    "enums": {
        "QuestCategoryId": {"11": "GlobalEventSolo"},
        "GlobalEventAction": {"3": "Hero_LevelUp"},
    },
}
NAMES = Names({}, {}, {}, {})
NOW = datetime(2026, 11, 27, tzinfo=UTC)


def test_decode_names_keys_enums_and_text() -> None:
    raw = {"i": 364549, "c": 11, "n": {"d": "Hero Level Up"}, "r": {"3": [1, 2]}, "zz": 1}

    assert decode(raw, "Quest", SCHEMA) == {
        "PrototypeId": 364549,
        "CategoryId": "GlobalEventSolo",
        "Name": "Hero Level Up",
        "Rules": {"Hero_LevelUp": [1, 2]},
    }


def test_texts_from_settings_ids() -> None:
    schema = {
        "classes": {
            "GlobalEventInterfaceSettingsDto": {
                "t": {"name": "TitleId", "type": "int"},
                "pn": {"name": "PointsNameId", "type": "Nullable<int>"},
            }
        },
        "enums": {},
    }
    texts = {260: "Champion Training Event", 1517: "Fate Points"}

    solo = parse_texts('{"t":260,"c":265,"pn":1517}', schema, texts)
    assert solo == EventTexts("Champion Training Event", "Fate Points")
    assert parse_texts(None, schema, texts) == EventTexts(None, None)


def test_tournament_ends_with_its_bracket() -> None:
    start = 1795690800000  # Thu 26 Nov 11:00 UTC
    two_days, three_days = 2 * 86_400_000, 3 * 864_000_000_000
    solo = {"Start": start, "End": start + two_days}
    tournament = {**solo, "BracketDuration": three_days}

    assert event_end(solo) == datetime(2026, 11, 28, 11, tzinfo=UTC)
    assert event_end(tournament) == datetime(2026, 11, 29, 11, tzinfo=UTC)


def test_rule_conditions_and_turn_points() -> None:
    rank = parse_rule("Artifact_Collect", {"Artifact": {"Rank": "Five", "Level": 0}, "Points": 7})
    assert rank == Rule("Artifact_Collect", (Condition("Artifact", "Rank", "Five"),), 7)

    turns = parse_rule(
        "Battle_DungeonTurn",
        {
            "Dungeon": {"Number": 25},
            "TurnAttackParameters": {
                "X": 2.68,
                "Y": -0.166,
                "S": 30,
                "MinPoints": 24,
                "MaxPoints": 80,
            },
        },
    )
    assert turns.points == TurnPoints(24, 80, 2.68, -0.166, 30)
    assert turns.conditions == (Condition("Dungeon", "Number", 25),)


def test_bracket_from_standing_else_levels() -> None:
    low, high = Bracket(1, 80, (Milestone(50, ()),)), Bracket(81, 100, (Milestone(100, ()),))
    joined, unjoined = event(1, brackets=(low, high)), event(2, brackets=(low, high))
    events = Events((joined, unjoined), {1: Standing(10, None, bracket=1)})
    levels = account_levels(events)

    assert levels == (81, 100)
    assert bracket_for(joined, events.standings[1], None) is high
    assert milestones_for(unjoined, None, levels) == high.milestones


def test_points_grid_when_rules_vary_along_two() -> None:
    rules = tuple(
        Rule("Artifact_Upgrade", (artifact("Rank", rank), artifact("Level", level)), points)
        for rank, level, points in [
            ("Five", 3, 0),
            ("Six", 3, 0),
            ("Five", 4, 2),
            ("Six", 4, 3),
            ("Five", 8, 5),
            ("Six", 8, 10),
        ]
    )
    (table,) = points_tables(rules, NAMES)

    assert table.side == "Level" and table.columns == ("5★", "6★")
    assert [(row.label, row.cells) for row in table.rows] == [
        ("+4", ("2", "3")),
        ("+8", ("5", "10")),
    ]


def test_points_rows_share_what_every_rule_sets() -> None:
    dungeon = Condition("Dungeon", "RegionTypeId", "ArtifactAscendDungeon")
    rules = (
        Rule(
            "Battle_DungeonTurn",
            (dungeon, stage("MinNumber", 1), stage("MaxNumber", 3)),
            turns(4, 13),
        ),
        Rule("Battle_DungeonTurn", (stage("Number", 25), dungeon), turns(24, 80)),
    )
    (table,) = points_tables(rules, NAMES)

    assert table.note == "Artifact Ascend Dungeon"
    assert [(row.label, row.cells) for row in table.rows] == [
        ("Stages 1–3", ("4–13",)),
        ("Stage 25", ("24–80",)),
    ]


def artifact(field: str, value: str | int) -> Condition:
    return Condition("Artifact", field, value)


def turns(least: int, most: int) -> TurnPoints:
    return TurnPoints(least, most, 2.68, -0.166, most / 2.68)


def stage(field: str, value: int) -> Condition:
    return Condition("Dungeon", field, value)


def event(prototype_id: int, brackets: tuple[Bracket, ...]) -> GameEvent:
    return GameEvent(
        id=prototype_id,
        prototype_id=prototype_id,
        name="Test",
        texts=EventTexts("Ice Golem Tournament", None),
        tournament=True,
        kind="IceGolem",
        teaser=None,
        start=NOW,
        end=NOW,
        claim_by=None,
        rules=(),
        milestones=(),
        brackets=brackets,
        highlights=(),
        max_points_per_day=None,
        rating_size=100,
    )


def test_turn_points_match_real_fights() -> None:
    sand_devil_25 = TurnPoints(24, 80, 2.68, -0.166, 30)

    assert (sand_devil_25.points(44), sand_devil_25.points(22)) == (43, 48)
    assert sand_devil_25.points(1) == 80 and sand_devil_25.points(5_000) == 24


def test_rules_add_where_they_hold() -> None:
    rules = (
        Rule("Hero_Summon", (Condition("Hero", "Rarity", "Epic"),), 250),
        Rule("Hero_Summon", (Condition("Hero", "Elements", ("Void",)),), 100),
        Rule("Hero_Summon", (Condition("Hero", "Fraction", "Undead"),), 1_000),
        Rule("Hero_LevelUp", (Condition("Hero", "Rarity", "Epic"),), 7),
    )

    assert rule_points(rules, "Hero_Summon", {"Rarity": "Epic", "Elements": "Void"}) == 350
    assert rule_points(rules, "Hero_Summon", {"Rarity": "Epic", "Elements": "Magic"}) == 250

    stages = (stage("MinNumber", 4), stage("MaxNumber", 7))
    assert [all(holds(c, {"Number": n}) for c in stages) for n in (3, 4, 7, 8)] == [
        False,
        True,
        True,
        False,
    ]


def test_events_not_loaded_yet(tmp_path) -> None:
    half_loaded = tmp_path / "events.json"
    half_loaded.write_text('{"json": "", "texts": {}, "progress": [], "summons": null}')

    assert load_events(half_loaded, tmp_path / "unread.json", tmp_path) is None
