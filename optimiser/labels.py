"""
labels.py - how stats and stat lines read, for every front end (CLI, web).

- `STAT_LABELS`, `PERCENT_STATS`: stat names as the game shows them, and which read in %
- `format_stat`, `format_line`, `line_label`, `line_amount`: the formatting
- `pool_choices`, `pool_name`, `pool_label`, `parse_pool`: gear pools, as offered, as a
  word ("all", "lock-3", "free") and as read
"""

import re

from optimiser.account import Stat, StatLine
from optimiser.solve import AnyGear, Pool, Unequipped, UpToLock
from optimiser.store import LOCK_LEVELS, Locks

STAT_LABELS = {
    Stat.HP: "HP",
    Stat.ATK: "ATK",
    Stat.DEF: "DEF",
    Stat.SPD: "SPD",
    Stat.RES: "RES",
    Stat.ACC: "ACC",
    Stat.CR: "C.RATE",
    Stat.CD: "C.DMG",
}
PERCENT_STATS = (Stat.CR, Stat.CD)


def format_stat(stat: Stat, value: float) -> str:
    """A champion's total in a stat."""
    return f"{value * 100:.0f}%" if stat in PERCENT_STATS else f"{value:.0f}"


def format_line(line: StatLine) -> str:
    """ "HP 60%", "SPD 17 (+3)": the line's amount, glyph included in brackets."""
    glyph = f" (+{line_amount(line.glyph, line.absolute)})" if line.glyph else ""
    return f"{line_label(line)} {line_amount(line.value, line.absolute)}{glyph}"


def line_label(line: StatLine) -> str:
    if line.stat:
        return STAT_LABELS[line.stat]

    return re.sub(r"(?<!^)(?=[A-Z])", " ", line.kind)  # "DealtDamageBoss" -> "Dealt Damage Boss"


def line_amount(value: float, absolute: bool) -> str:
    return f"{value:g}" if absolute else f"{value * 100:.3g}%"


def pool_choices(locks: Locks) -> list[Pool]:
    """Loosest first. Up to the top lock level would be the same as any gear, so it's left
    out."""
    lock_levels = range(max(LOCK_LEVELS) - 1, -1, -1)
    return [AnyGear(), *(UpToLock(level, locks) for level in lock_levels), Unequipped()]


def pool_name(pool: Pool) -> str:
    match pool:
        case AnyGear():
            return "all"

        case Unequipped():
            return "free"

        case UpToLock(level=level):
            return f"lock-{level}"


def pool_label(pool: Pool) -> str:
    match pool:
        case AnyGear():
            return "Any"

        case Unequipped():
            return "Unequipped only"

        case UpToLock(level=0):
            return "Unlocked only"

        case UpToLock(level=level):
            return f"Locked up to {level}"


def parse_pool(name: str, locks: Locks) -> Pool | None:
    """None for a name `pool_name` never gives."""
    match name.split("-"):
        case ["all"]:
            return AnyGear()

        case ["free"]:
            return Unequipped()

        case ["lock", level] if level.isdigit() and int(level) <= max(LOCK_LEVELS):
            return UpToLock(int(level), locks)

        case _:
            return None
