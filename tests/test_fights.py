"""
test_fights.py - reading the battle host's results (`optimiser.fights`) on a made-up
`BattleResult`, in the game's JSON shape.

- `test_rows_count_once_each`: two alike Poison ticks both count; a row filed under its target
  too counts once
- `test_dealt_taken_healed`: hits on the boss are dealt, the boss's hits taken, heals healed
- `test_boss_turns`: the boss's turns, summed over rounds
- `test_differences`: a replay against the game's record, row by row
- `test_turn_limit_clears_unkillable`: lasting to the turn limit clears a boss that can't die,
  not one that can
- `test_trials`: the Chimera's trials from the final state, and a replay's checked against them
- `test_a_round_without_turns`: a round the game left no rows in (a Hydra head grown again)
"""

import json
from pathlib import Path

from dataclasses import replace

from optimiser.fights import HeroTypes, differences, read_fight

TYPES = HeroTypes(
    {3506: "Venus", 9956: "Donatello", 28016: "Tainted Demon Lord"}, frozenset({28016})
)


def row(producer: int, target: int, damage: int = 0, healed: int = 0) -> dict:
    return {"z": producer, "x": target, "d": damage, "h": healed}


def hero(owner: int, type_id: int, turns: list[list[dict]], boss_turns: int = 0) -> dict:
    by_turn = {str(i): rows for i, rows in enumerate(turns)}
    return {"o": owner, "t": type_id, "r": {"1": {"r": by_turn, "t": boss_turns}}}


def write(tmp_path: Path, heroes: dict[int, dict], **result) -> Path:
    path = tmp_path / "result-0.json"
    path.write_text(json.dumps({"x": {"d": {str(i): h for i, h in heroes.items()}}, **result}))
    return path


def fight(tmp_path: Path, boss: int = 28016, **result):
    poison = row(0, 5, damage=50_000)
    heroes = {
        0: hero(1, 3506, [[poison, dict(poison)]]),
        4: hero(1, 9956, [[row(4, 5, damage=20_000), row(4, 0, healed=3_000)]]),
        5: hero(-1, boss, [[row(5, 0, damage=700), row(0, 5, damage=50_000)]], boss_turns=7),
    }
    return read_fight(write(tmp_path, heroes, **result), TYPES)


def test_rows_count_once_each(tmp_path: Path) -> None:
    venus = fight(tmp_path).champions[0]

    assert venus.dealt == 100_000


def test_dealt_taken_healed(tmp_path: Path) -> None:
    venus, donatello = fight(tmp_path).champions

    assert (donatello.dealt, donatello.healed) == (20_000, 3_000)
    assert (venus.taken, donatello.taken) == (700, 0)


def test_boss_turns(tmp_path: Path) -> None:
    result = fight(tmp_path)

    assert result.boss_turns == 7
    assert result.damage == 120_000


def test_differences(tmp_path: Path) -> None:
    real = fight(tmp_path)
    venus, donatello = real.champions
    sim = replace(real, turns=real.turns + 1, champions=(replace(venus, dealt=99), donatello))

    assert differences(real, real) == []
    assert differences(sim, real) == [
        "turns: game 0, replay 1",
        "Venus dealt: game 100,000, replay 99",
    ]


def test_turn_limit_clears_unkillable(tmp_path: Path) -> None:
    lasted = fight(tmp_path, i=2, c=2)
    wiped = fight(tmp_path, i=2, c=0)
    dungeon = fight(tmp_path, boss=9956, i=2, c=2)

    assert (lasted.cleared, lasted.unkillable) == (True, True)
    assert (wiped.cleared, wiped.ending) == (False, "team defeated")
    assert (dungeon.cleared, dungeon.ending) == (False, "turn limit")


def test_trials(tmp_path: Path) -> None:
    trials = {"8000613": {"s": 1, "t": 16}, "8000602": {"s": 0}}
    real = fight(tmp_path, s={"s": {"h": [{"ch": trials}]}})
    sim = replace(real, trials={8000613: 16, 8000602: 40})

    assert real.trials == {8000613: 16, 8000602: None}
    assert differences(sim, real) == ["trial 8000602 completed: game None, replay 40"]


def test_a_round_without_turns() -> None:
    """A Hydra head grown again may have a round with no turns: the game leaves out its rows."""
    from optimiser.fights import rows_of

    hero = {"r": {"1": {"t": 0}, "2": {"r": {"3": [{"z": 1, "x": 2, "d": 5, "h": None}]}}}}

    assert rows_of(hero) == [{"z": 1, "x": 2, "d": 5, "h": None}]
