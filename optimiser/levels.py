"""
levels.py - base stats by rank and level, computed as the game does (read from
`SharedModel.Meta.Heroes.BattleStats.BuildFromBase` / `CalcValue` disassembly, 11.85.5).

The static data holds unscaled stats (HP ÷ 15, crit in %). For rank g and level L, HP, ATK
and DEF are `Round(base × a × b^((L − 1) / (10g − 1)))` with (a, b) = `MULTIPLIERS[g − 1]`
(the game's `BattleStats.Multipliers`, filled from metadata), in Plarium's Q32.32 `Fixed`
arithmetic: doubles convert by truncation, products floor, the round is half to even. HP is
then × 15. SPD, RES and ACC are unscaled; C.RATE and C.DMG are divided by 100.

- `MULTIPLIERS`, `MULTIPLIERS_BLOB`: the game's table, and its bytes in the metadata
- `base_stats`: a form's base stats at a rank and level
- `scale`: one HP/ATK/DEF value
- `to_fixed`, `multiply`, `round_even`: the `Fixed` operations it uses
"""

import math
import struct

from optimiser.account import Stat, Stats

MULTIPLIERS = (
    (1.0, 2.0),
    (1.6, 1.9),
    (2.432, 1.8),
    (3.50208, 1.7),
    (4.7628288, 1.7),
    (6.477447168, 1.7),
)

# How the table sits in global-metadata.dat (`tools/check_levels.py` looks for it there).
MULTIPLIERS_BLOB = struct.pack("<12d", *(x for row in MULTIPLIERS for x in row))

FRACTION_BITS = 32
ONE = 1 << FRACTION_BITS
HALF = ONE >> 1

# Static data holds HP divided by 15 and crit in %.
UNSCALED_HP = 15
PERCENT = 100


def base_stats(unscaled: Stats, grade: int, level: int) -> Stats:
    """A form's base stats at rank `grade` (1-6), level `level`, from its unscaled stats."""
    scaled = {
        Stat.HP: scale(unscaled.get(Stat.HP, 0), grade, level) * UNSCALED_HP,
        Stat.ATK: scale(unscaled.get(Stat.ATK, 0), grade, level),
        Stat.DEF: scale(unscaled.get(Stat.DEF, 0), grade, level),
        Stat.CR: unscaled.get(Stat.CR, 0) / PERCENT,
        Stat.CD: unscaled.get(Stat.CD, 0) / PERCENT,
    }
    return {stat: scaled.get(stat, unscaled.get(stat, 0)) for stat in Stat}


def scale(base: float, grade: int, level: int) -> int:
    """`CalcValue`: one HP (÷ 15), ATK or DEF value at a rank and level."""
    a, b = MULTIPLIERS[grade - 1]
    exponent = (level - 1.0) / (10 * grade - 1)
    raw = multiply(multiply(round(base * ONE), to_fixed(a)), to_fixed(math.pow(b, exponent)))
    return round_even(raw) >> FRACTION_BITS


def to_fixed(value: float) -> int:
    """`Fixed(double)`: scaled by 2^32, truncated toward zero."""
    return int(value * ONE)


def multiply(x: int, y: int) -> int:
    """`Fixed * Fixed` for the non-negative values here: the product's floor."""
    return (x * y) >> FRACTION_BITS


def round_even(raw: int) -> int:
    """`FixedMath.Round(value, MidpointRounding.ToEven)`."""
    floor = raw & ~(ONE - 1)
    fraction = raw & (ONE - 1)

    if fraction > HALF or (fraction == HALF and floor & ONE):
        return floor + ONE

    return floor
