"""
accuracy.py - the chance a debuff is resisted, as the game rolls it (`EffectManager.IsResisted`,
read from the game code). With d = the target's RES - the caster's ACC:

  d < 30:  3 % + 27 % e^(6 (d/100 - 0.3))          (falls towards 3 % as ACC passes RES)
  d >= 30: 30 % + 67 % (1 - e^(-3 (d/100 - 0.3)))  (rises towards 97 %)

So nothing lands more than 97 % of the time, and ACC only approaches that. The skill's own
chance is rolled apart. Left out, as gear doesn't change them: a skill's ignore-RES (RES ×
(1 - it)) and per-application ACC/RES modifiers (neither goes below 0).

- `RESIST_FLOOR`, `RESIST_CAP`, `BEND`, `NEAR_FLOOR`: the game's constants, and how close to
  the floor counts as at it
- `resist_chance`, `accuracy_for_floor`, `resistance_for_cap`: the model
"""

import math

RESIST_FLOOR = 0.03
RESIST_CAP = 0.97
BEND = 30  # RES over ACC where the two curves meet, at 30 % resisted
NEAR_FLOOR = 0.001  # within 0.1 percentage points of the floor counts as at it


def resist_chance(accuracy: float, resistance: float) -> float:
    over = (resistance - accuracy) / 100 - BEND / 100

    if over < 0:
        return RESIST_FLOOR + 0.27 * math.exp(6 * over)

    return 0.30 + (RESIST_CAP - 0.30) * (1 - math.exp(-3 * over))


def accuracy_for_floor(resistance: float) -> int:
    """The least whole ACC whose resist chance is within `NEAR_FLOOR` of the floor."""
    # 0.27 e^(6 (d/100 - 0.3)) <= NEAR_FLOOR, solved for d (negative: ACC over RES).
    most_over = 100 * (math.log(NEAR_FLOOR / 0.27) / 6 + BEND / 100)
    return math.ceil(resistance - most_over)


def resistance_for_cap(accuracy: float) -> int:
    """The least whole RES that resists within `NEAR_FLOOR` of the cap, against `accuracy`."""
<<<<<<< Updated upstream
    # (RESIST_CAP - 0.30) e^(-3 (d/100 - 0.3)) <= NEAR_FLOOR, solved for d.
    least_over = 100 * (math.log((RESIST_CAP - 0.30) / NEAR_FLOOR) / 3 + BEND / 100)
    return math.ceil(accuracy + least_over)
=======
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
>>>>>>> Stashed changes
