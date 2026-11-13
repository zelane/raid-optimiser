"""
test_damage.py - skill formulas as linear functions of the champion's stats.

- `test_plus_keeps_first_seen_order`: summing formulas doesn't reorder their stats
"""

import subprocess
import sys
from pathlib import Path

from optimiser.account import Stat
from optimiser.damage import LinearFormula, parse_formula

# Run in fresh interpreters: a set's order over StrEnum members changes with the hash seed.
ROOT = Path(__file__).resolve().parents[1]
SEEDS = ("0", "1", "2", "3", "4", "5", "6", "7")
PROBE = (
    "from optimiser.damage import parse_formula;"
    "print(list(parse_formula('6*ATK + 0.4*HP').coefficients))"
)


def test_plus_keeps_first_seen_order() -> None:
    total = LinearFormula({Stat.ATK: 6.0}).plus(LinearFormula({Stat.HP: 0.4, Stat.ATK: 1.0}))
    assert list(total.coefficients) == [Stat.ATK, Stat.HP]
    assert total.coefficients == {Stat.ATK: 7.0, Stat.HP: 0.4}

    formula = parse_formula("6*ATK + 0.4*HP")
    assert formula is not None
    assert list(formula.coefficients) == [Stat.ATK, Stat.HP]

    orders = {
        subprocess.run(
            [sys.executable, "-c", PROBE],
            env={"PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in SEEDS
    }
    assert len(orders) == 1, orders
