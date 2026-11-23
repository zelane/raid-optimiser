"""
test_rate_goals.py - rates as goals the solver ranks (`accuracy.Lands`, `accuracy.Resists`):
ranked as their stat capped where the rate stops rising, held within the slack of their best
rate.

- `test_most_useful`: the cap is where the rate is within 0.1 points of the floor or cap
- `test_held_floor_keeps_the_rate`: the hold's least stat keeps the rate within the slack
- `test_held_floor_never_above_best`: rounding the stat up never asks more than the best
- `test_ranking_stops_at_the_floor`: on the account, ACC past the rate's need goes to the next
  goal
"""

import pytest

from optimiser.account import Stat
from optimiser.accuracy import RESIST_FLOOR, Lands, Resists, resist_chance
from optimiser.paths import GAME, SCHEMA, SNAPSHOT
from optimiser.solve import held_floor


def test_most_useful() -> None:
    lands, resists = Lands(250), Resists(300)
    assert resist_chance(lands.most_useful(), 250) <= RESIST_FLOOR + 0.001
    assert resist_chance(300, resists.most_useful()) >= 0.97 - 0.001


@pytest.mark.parametrize("goal", [Lands(250), Resists(300)])
@pytest.mark.parametrize("best", [150.0, 230.0, 280.0, 400.0])
def test_held_floor_keeps_the_rate(goal, best: float) -> None:
    slack = 0.05
    floor = held_floor(goal, best, slack)
    assert floor <= best
    assert goal.rate(floor) >= goal.rate(best) * (1 - slack) - 1e-9
    assert floor in (0, best) or goal.rate(floor - 1) < goal.rate(best) * (1 - slack)


def test_held_floor_never_above_best() -> None:
    assert held_floor(Lands(250), 263.4, 0.0) == 263.4


def test_ranking_stops_at_the_floor() -> None:
    """Debuffs landing, then HP: the land rate is held within the slack of its best and the
    rest goes to HP, which ACC then HP (ranking the stat itself) can't do."""
    if not SNAPSHOT.exists():
        pytest.skip("no account snapshot (just read)")

    from optimiser.account import load_account
    from optimiser.solve import GearFilter, Request, find_builds

    account = load_account(SNAPSHOT, GAME, SCHEMA)
    champion = max(account.champions.values(), key=lambda c: (c.grade, c.level))
    resistance = 150.0

    def best(*ranking) -> dict:
        request = Request(
            champion=champion,
            minimums={},
            maximums={},
            set_minimums={},
            ranking=ranking,
            slack=0.01,
            builds=1,
            gear=GearFilter(),
            above_level=8,
        )
        (build,) = find_builds(account, request)
        return build.stats

    lands = Lands(resistance)
    by_rate = best(lands, Stat.HP)
    by_stat = best(Stat.ACC, Stat.HP)
    best_rate = lands.rate(min(by_stat[Stat.ACC], lands.most_useful()))
    assert lands.rate(by_rate[Stat.ACC]) >= best_rate * (1 - 0.01) - 1e-9
    assert by_rate[Stat.HP] >= by_stat[Stat.HP]
