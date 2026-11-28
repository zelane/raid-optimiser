"""
test_fights.py - reading the battle host's results (`optimiser.fights`) on a made-up
`BattleResult`, in the game's JSON shape.

- `test_rows_count_once_each`: two alike Poison ticks both count; a row filed under its target
  too counts once
- `test_dealt_taken_healed`: hits on the boss are dealt, the boss's hits taken, heals healed
- `test_boss_turns`: the boss's turns, summed over rounds
- `test_differences`: a replay against the game's record, row by row
"""

import json
from pathlib import Path

from dataclasses import replace

from optimiser.fights import differences, read_fight

NAMES = {3506: "Venus", 9956: "Donatello", 28016: "Tainted Demon Lord"}


def row(producer: int, target: int, damage: int = 0, healed: int = 0) -> dict:
    return {"z": producer, "x": target, "d": damage, "h": healed}


def hero(owner: int, type_id: int, turns: list[list[dict]], boss_turns: int = 0) -> dict:
    by_turn = {str(i): rows for i, rows in enumerate(turns)}
    return {"o": owner, "t": type_id, "r": {"1": {"r": by_turn, "t": boss_turns}}}


def write(tmp_path: Path, heroes: dict[int, dict]) -> Path:
    path = tmp_path / "result-0.json"
    path.write_text(json.dumps({"x": {"d": {str(i): h for i, h in heroes.items()}}}))
    return path


def fight(tmp_path: Path):
    poison = row(0, 5, damage=50_000)
    heroes = {
        0: hero(1, 3506, [[poison, dict(poison)]]),
        4: hero(1, 9956, [[row(4, 5, damage=20_000), row(4, 0, healed=3_000)]]),
        5: hero(-1, 28016, [[row(5, 0, damage=700), row(0, 5, damage=50_000)]], boss_turns=7),
    }
    return read_fight(write(tmp_path, heroes), NAMES)


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
    assert differences(sim, real) == ["turns: game 0, replay 1", "Venus dealt: game 100,000, replay 99"]
