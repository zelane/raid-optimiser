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
    # (RESIST_CAP - 0.30) e^(-3 (d/100 - 0.3)) <= NEAR_FLOOR, solved for d.
    least_over = 100 * (math.log((RESIST_CAP - 0.30) / NEAR_FLOOR) / 3 + BEND / 100)
    return math.ceil(accuracy + least_over)
