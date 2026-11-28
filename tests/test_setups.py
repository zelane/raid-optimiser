"""
test_setups.py - writing the account as the game's JSON for the battle host
(`optimiser.setups`), on made-up records.

- `test_bonus_keeps_the_raw_fixed`: a line's `Fixed` values are the reader's raw ones, and a
  Mythical line's rarity glyph goes along
- `test_skill_setups`: the hero type's order, and a copy skill at its source's level
- `test_relic_setup`: skills at the level the relic's level reaches, stones' skills, crit as a
  percentage
- `test_team_setup`: the template's enemies stay, the team's slots are numbered
- `test_turn_limit`: everyone's turns, an area's own, the co-op boss's turns
"""

from optimiser.setups import (
    Enums,
    Relics,
    game_bonus,
    relic_setup,
    skill_setups,
    team_setup,
    turn_limit,
)

ENUMS = Enums({"StatKindId": {"Speed": 4, "CriticalDamage": 8}})


def test_bonus_keeps_the_raw_fixed() -> None:
    line = {
        "stat": "Speed",
        "absolute": True,
        "value": 10.0,
        "glyph": 0.0,
        "rolls": 1,
        "value_fixed": 42949672960,
        "glyph_fixed": 0,
        "rarity_glyph_fixed": 21474836480,
        "glyph_rarity": 6,
    }

    assert game_bonus(line, ENUMS) == {
        "k": 4,
        "p": {"a": True, "v": 42949672960},
        "s": 0,
        "l": 1,
        "r": 21474836480,
        "i": 6,
    }


def test_skill_setups() -> None:
    hero = {"skills": {"99501": 4, "99504": 3, "99505": 1, "99502": 2}}
    skills = {"99505": {"use_level_of": 99501}}

    setups = skill_setups(hero, [[99501, 99502, 99505, 99504]], skills)

    assert setups == [
        {"i": 99501, "l": 4},
        {"i": 99502, "l": 2},
        {"i": 99505, "l": 4},
        {"i": 99504, "l": 3},
    ]


def test_relic_setup() -> None:
    sources = {
        "relics": [{"id": 16, "skills": [3000015], "by_faction": {"Shadowkin": [3000099]}}],
        "relic_skill_levels": {"0": 1, "6": 2, "9": 3, "12": 4},
        "relic_stones": {"32": {"skills": [4000031]}},
    }
    relics = Relics({}, {142: {"id": 142, "type_id": 32}}, sources)
    relic = {"type_id": 16, "level": 12, "sockets": [{"shape": 1, "stone": 142}, {"stone": None}]}
    built = {"p": {}, "f": {"d": 255, "m": 1116691496}}

    setup = relic_setup(relic, built, relics, "Shadowkin")

    assert setup == {
        "l": 4,
        "r": [{"i": 3000015, "l": 4}, {"i": 3000099, "l": 4}],
        "s": [{"i": 4000031, "l": 0}],
        "p": {"m": 1116691496},
        "f": {"d": 255},
    }


def test_team_setup() -> None:
    template = {"i": 15019005, "f": {"i": 1, "h": [{"h": 9}]}, "s": {"h": [{"h": 0}]}}

    setup = team_setup(template, [{"h": 1}, {"h": 2}])

    assert setup["s"] == template["s"]
    assert setup["f"]["h"] == [{"h": 1, "t": 1}, {"h": 2, "t": 2}]


def test_turn_limit() -> None:
    enums = Enums({"AreaTypeId": {"Dungeon": 2, "Hydra": 8}})
    settings = {
        "MaxTurnsInBattle": 1500,
        "SpecificMaxTurnsInBattleByArea": {"8": 1000},
        "WorldBossTurnLimit": 75,
    }

    assert turn_limit("Dungeon", settings, enums) == {"mt": 1500}
    assert turn_limit("Hydra", settings, enums) == {"mt": 1000}
    assert turn_limit("CooperationEventWorldBoss", settings, enums) == {"bt": 75}
