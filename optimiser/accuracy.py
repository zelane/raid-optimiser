"""
accuracy.py - the chance a debuff is resisted, as the game rolls it (`EffectManager.IsResisted`),
in its `Fixed` arithmetic (checked against the game's code by tests/test_game_code.py). With
d = the target's RES - the caster's ACC:

  d < 30:  3 % + 27 % e^(6 (d/100 - 0.3))          (falls towards 3 % as ACC passes RES)
  d >= 30: 30 % + 67 % (1 - e^(3 (0.3 - d/100)))   (rises towards 97 %)

Resisted when a roll in [0, 1) is at most that. So nothing lands more than 97 % of the time,
and ACC only approaches that. The skill's own chance is rolled apart. Left out, as gear doesn't
change them: a skill's ignore-RES (RES × (1 - it)) and per-application ACC/RES modifiers
(neither goes below 0).

Rates turn into stats the other way: the least whole ACC for a resisted rate against a RES, the
least whole RES for a resisting rate against an ACC (what a rate target asks of gear).

- `RESIST_FLOOR`, `RESIST_CAP`, `BEND`, `NEAR_FLOOR`: the game's constants, and how close to
  the floor counts as at it
- `resist_chance`, `landing_chance`: the rates
- `accuracy_for_resisted`, `resistance_for_resisting`: the stats for a rate
- `accuracy_for_floor`, `resistance_for_cap`: those at the floor and cap
- `Lands`, `Resists`, `RateGoal`: rates as goals the solver ranks
- `resist_threshold`: the game's computation, in `Fixed`
"""

from dataclasses import dataclass

from optimiser import fixed
from optimiser.account import Stat
from optimiser.fixed import ONE, Fixed

RESIST_FLOOR = 0.03
RESIST_CAP = 0.97
BEND = 30  # RES over ACC where the two curves meet, at 30 % resisted
NEAR_FLOOR = 0.001  # within 0.1 percentage points of the floor counts as at it


def resist_chance(accuracy: float, resistance: float) -> float:
    """The chance a debuff is resisted."""
    return fixed.to_float(resist_threshold(fixed.of(accuracy), fixed.of(resistance)))


def landing_chance(skill_chance: float, accuracy: float, resistance: float) -> float:
    """The chance a debuff lands: its own chance, then not resisted (rolled apart)."""
    return skill_chance * (1 - resist_chance(accuracy, resistance))


def accuracy_for_resisted(resisted: float, resistance: float) -> int | None:
    """The least whole ACC (0 or more) whose debuffs are resisted at most `resisted` of the
    time against `resistance`, or None if no ACC gets there (the floor is 3 %)."""
    return least_whole(lambda accuracy: resist_chance(accuracy, resistance) <= resisted)


def resistance_for_resisting(resisting: float, accuracy: float) -> int | None:
    """The least whole RES (0 or more) that resists at least `resisting` of `accuracy`'s
    debuffs, or None if no RES gets there (97 %; `Fixed` holds the cap a hair below it)."""
    return least_whole(lambda resistance: resist_chance(accuracy, resistance) >= resisting)


def accuracy_for_floor(resistance: float) -> int:
    """The least whole ACC whose resist chance is within `NEAR_FLOOR` of the floor."""
    accuracy = accuracy_for_resisted(RESIST_FLOOR + NEAR_FLOOR, resistance)
    assert accuracy is not None
    return accuracy


def resistance_for_cap(accuracy: float) -> int:
    """The least whole RES that resists within `NEAR_FLOOR` of the cap, against `accuracy`."""
    resistance = resistance_for_resisting(RESIST_CAP - NEAR_FLOOR, accuracy)
    assert resistance is not None
    return resistance


@dataclass(frozen=True)
class Lands:
    """A goal: the champion's debuffs landing against a RES. Ranks ACC by how rarely it's
    resisted, so ACC past the `target` rate (none: the floor, `accuracy_for_floor`) is worth
    nothing more."""

    resistance: float
    target: float | None = None
    stat = Stat.ACC

    def rate(self, accuracy: float) -> float:
        return 1 - resist_chance(accuracy, self.resistance)

    def most_useful(self) -> int:
        floor = accuracy_for_floor(self.resistance)
        least = None if self.target is None else self.least_for(self.target)
        return floor if least is None else min(least, floor)

    def least_for(self, rate: float) -> int | None:
        """The least ACC that lands `rate` of the time (None: none does)."""
        return accuracy_for_resisted(1 - rate, self.resistance)


@dataclass(frozen=True)
class Resists:
    """A goal: the champion resisting debuffs from an ACC. Ranks RES by how often it resists,
    so RES past the `target` rate (none: the cap, `resistance_for_cap`) is worth nothing
    more."""

    accuracy: float
    target: float | None = None
    stat = Stat.RES

    def rate(self, resistance: float) -> float:
        return resist_chance(self.accuracy, resistance)

    def most_useful(self) -> int:
        cap = resistance_for_cap(self.accuracy)
        least = None if self.target is None else self.least_for(self.target)
        return cap if least is None else min(least, cap)

    def least_for(self, rate: float) -> int | None:
        """The least RES that resists `rate` of the time (None: none does)."""
        return resistance_for_resisting(rate, self.accuracy)


type RateGoal = Lands | Resists


def resist_threshold(accuracy: Fixed, resistance: Fixed) -> Fixed:
    """`IsResisted`'s chance: resisted when the roll is at most this."""
    over = fixed.sub(resistance, accuracy)
    hundredths = fixed.div(over, fixed.of_int(100))

    if over < fixed.of_int(BEND):
        rising = fixed.exp(fixed.mul(fixed.of_int(6), fixed.sub(hundredths, fixed.of(0.3))))
        return fixed.add(fixed.of(0.03), fixed.mul(fixed.of(0.27), rising))

    falling = fixed.exp(fixed.mul(fixed.of_int(3), fixed.sub(fixed.of(0.3), hundredths)))
    return fixed.add(fixed.of(0.3), fixed.mul(fixed.of(0.67), fixed.sub(ONE, falling)))


HIGHEST_STAT = 100_000  # past any stat a build reaches


def least_whole(holds) -> int | None:
    """The least whole number in [0, `HIGHEST_STAT`] that `holds` (monotone: false below it,
    true from it), or None if none does: a binary search."""
    if not holds(HIGHEST_STAT):
        return None

    low, high = -1, HIGHEST_STAT  # not holds(low) (or below range), holds(high)
    while high - low > 1:
        middle = (low + high) // 2
        if holds(middle):
            high = middle
        else:
            low = middle

    return high
