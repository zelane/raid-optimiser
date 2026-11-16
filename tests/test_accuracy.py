"""
test_accuracy.py - the resist roll's chance against ACC and RES (`optimiser.accuracy`).

- `test_curves_meet_at_the_bend`: both pieces give 30 % at RES = ACC + 30
- `test_bounds`: 3 % floor and 97 % cap, approached, never passed
- `test_known_points`: values read off the formula by hand
- `test_accuracy_for_floor`: the least ACC within 0.1 points of the floor
- `test_resistance_for_cap`: the least RES within 0.1 points of the cap
"""

import pytest

from optimiser.accuracy import (
    NEAR_FLOOR,
    RESIST_CAP,
    RESIST_FLOOR,
    accuracy_for_floor,
    resist_chance,
    resistance_for_cap,
)


def test_curves_meet_at_the_bend() -> None:
    assert resist_chance(100, 130) == pytest.approx(0.30)
    assert resist_chance(100, 129.999) == pytest.approx(0.30, abs=1e-4)


def test_bounds() -> None:
    assert RESIST_FLOOR <= resist_chance(1000, 0) < RESIST_FLOOR + 1e-9
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
