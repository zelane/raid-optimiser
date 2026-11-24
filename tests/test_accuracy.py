"""
test_accuracy.py - the resist roll's chance against ACC and RES (`optimiser.accuracy`).

- `test_curves_meet_at_the_bend`: both pieces give 30 % at RES = ACC + 30
- `test_bounds`: 3 % floor and 97 % cap (as `Fixed` holds them), approached, never passed
- `test_known_points`: values read off the formula by hand
- `test_accuracy_for_floor`: the least ACC within 0.1 points of the floor
- `test_resistance_for_cap`: the least RES within 0.1 points of the cap
- `test_rates_to_stats`: the least ACC / RES for a rate, and rates no stat reaches
- `test_landing_chance`: the skill's chance, then not resisted
"""

import pytest

from optimiser import fixed
from optimiser.accuracy import (
    NEAR_FLOOR,
    RESIST_CAP,
    RESIST_FLOOR,
    accuracy_for_floor,
    accuracy_for_resisted,
    landing_chance,
    resist_chance,
    resistance_for_cap,
    resistance_for_resisting,
)


def test_curves_meet_at_the_bend() -> None:
    assert resist_chance(100, 130) == pytest.approx(0.30)
    assert resist_chance(100, 129.999) == pytest.approx(0.30, abs=1e-4)


def test_bounds() -> None:
    floor = fixed.to_float(fixed.of(RESIST_FLOOR))  # 0.0299999998: (Fixed)0.03 truncates
    assert floor <= resist_chance(1000, 0) < floor + 1e-9
    assert 0.97 - 1e-9 < resist_chance(0, 1000) < 0.97


def test_known_points() -> None:
    assert resist_chance(225, 225) == pytest.approx(0.0746, abs=1e-4)
    assert resist_chance(255, 225) == pytest.approx(0.0374, abs=1e-4)
    assert resist_chance(175, 225) == pytest.approx(0.6023, abs=1e-4)


def test_accuracy_for_floor() -> None:
    accuracy = accuracy_for_floor(225)
    assert accuracy == 225 + 64
    assert resist_chance(accuracy, 225) <= RESIST_FLOOR + NEAR_FLOOR
    assert resist_chance(accuracy - 1, 225) > RESIST_FLOOR + NEAR_FLOOR


def test_resistance_for_cap() -> None:
    resistance = resistance_for_cap(225)
    assert resistance == 225 + 247
    assert resist_chance(225, resistance) >= RESIST_CAP - NEAR_FLOOR
    assert resist_chance(225, resistance - 1) < RESIST_CAP - NEAR_FLOOR


@pytest.mark.parametrize("rate", [0.031, 0.05, 0.1, 0.3, 0.5, 0.9])
def test_rates_to_stats(rate: float) -> None:
    accuracy = accuracy_for_resisted(rate, 250)
    assert accuracy is not None
    assert resist_chance(accuracy, 250) <= rate < resist_chance(accuracy - 1, 250)

    resistance = resistance_for_resisting(rate, 250)
    assert resistance is not None
    assert resist_chance(250, resistance - 1) < rate <= resist_chance(250, resistance)


def test_rates_no_stat_reaches() -> None:
    assert accuracy_for_resisted(0.02, 250) is None
    assert resistance_for_resisting(0.98, 250) is None


def test_landing_chance() -> None:
    assert landing_chance(0.5, 225, 225) == pytest.approx(0.5 * (1 - 0.0746), abs=1e-4)
