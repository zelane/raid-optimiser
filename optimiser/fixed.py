"""
fixed.py - the game's `Fixed` (Plarium.Common.Numerics): a signed Q32.32 number held as an
int64, and the operations the battle code does with it, bit for bit (read from the game's code
and checked against it by tests/test_game_code.py).

A `Fixed` here is its raw int64 value, so `ONE` is 2^32.

- `ONE`, `MAX`, `MIN`, `Fixed`: the representation
- `of`, `of_int`, `to_float`: conversions (`(Fixed)double` truncates)
- `add`, `sub`, `mul`, `div`: arithmetic (saturating; products floor, quotients round)
- `exp`, `clamp`: `FixedMath`'s
"""

import math

type Fixed = int  # the raw int64: value × 2^32

FRACTION_BITS = 32
ONE: Fixed = 1 << FRACTION_BITS
MAX: Fixed = (1 << 63) - 1
MIN: Fixed = -(1 << 63)


def of(value: float) -> Fixed:
    """`(Fixed)double`: scaled by 2^32 and truncated toward zero (`cvttsd2si`)."""
    return int(value * ONE)


def of_int(value: int) -> Fixed:
    return value << FRACTION_BITS


def to_float(value: Fixed) -> float:
    """`(double)Fixed`."""
    return value / ONE


def add(x: Fixed, y: Fixed) -> Fixed:
    """`x + y`, saturating at `MAX` / `MIN`."""
    return saturate(x + y)


def sub(x: Fixed, y: Fixed) -> Fixed:
    return saturate(x - y)


def mul(x: Fixed, y: Fixed) -> Fixed:
    """`x * y`: the product's floor, saturating."""
    return saturate((x * y) >> FRACTION_BITS)


def div(x: Fixed, y: Fixed) -> Fixed:
    """`x / y`: the quotient's magnitude rounded half up, then signed."""
    magnitude = ((abs(x) << (FRACTION_BITS + 1)) // abs(y) + 1) >> 1
    return saturate(magnitude if (x < 0) == (y < 0) else -magnitude)


def exp(x: Fixed) -> Fixed:
    """`FixedMath.Exp`: `(Fixed)Math.Exp((double)x)`."""
    return of(math.exp(to_float(x)))


def clamp(x: Fixed, low: Fixed, high: Fixed) -> Fixed:
    return max(low, min(x, high))


def saturate(raw: int) -> Fixed:
    return max(MIN, min(raw, MAX))
