"""
labels.py - how stats and stat lines read, for every front end (CLI, web).

- `STAT_LABELS`, `PERCENT_STATS`: stat names as the game shows them, and which read in %
- `format_stat`, `format_line`, `line_label`, `line_amount`: the formatting
- `glyph_kind_label`, `glyph_grade_label`: glyphs, "HP%", "6★ Legendary"
- `gear_filter_label`: what a solve keeps out of its gear, in a line
- `MARKER_LABELS`, `rule_label`, `reason_label`: champion tags as the game shows them, and
  what reserves gear: "Arena Build I", "team cb"; "Arena Build I (Arbiter)", "preset spd"
"""

import re

from optimiser.account import Account, GlyphGrade, GlyphKind, Stat, StatLine
from optimiser.reserve import GlobalPresets, Held, Reason, Rule, Tagged, Team, Worn
from optimiser.solve import GearFilter

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
MARKER_LABELS = {
    "Favorite": "Favorite",
    "First": "Build I",
    "Second": "Build II",
    "Third": "Build III",
    "Attack": "Attack Build",
    "Defence": "Defense Build",
    "Support": "Support Build",
    "Speed": "Speed Build",
    "ArenaFirst": "Arena Build I",
    "ArenaSecond": "Arena Build II",
}


def format_stat(stat: Stat, value: float) -> str:
    """A champion's total in a stat."""
    return f"{value * 100:.0f}%" if stat in PERCENT_STATS else f"{value:.0f}"


def format_line(line: StatLine) -> str:
    """ "HP 60%", "SPD 17 (+3)", "SPD 17 (+12 to glyph)", "HP 2631->4080": the line's amount,
    glyph included in brackets (an assumed one if it's better), and any assumed value."""
    if line.planned_glyph:
        glyph = f" (+{line_amount(line.planned_glyph, line.absolute)} to glyph)"
    elif line.glyph:
        glyph = f" (+{line_amount(line.glyph, line.absolute)})"
    else:
        glyph = ""

    amount = line_amount(line.value, line.absolute)

    if line.planned_value is not None:
        amount += "->" + line_amount(line.planned_value, line.absolute)

    return f"{line_label(line)} {amount}{glyph}"


def line_label(line: StatLine) -> str:
    if line.stat:
        return STAT_LABELS[line.stat]

    return re.sub(r"(?<!^)(?=[A-Z])", " ", line.kind)  # "DealtDamageBoss" -> "Dealt Damage Boss"


def line_amount(value: float, absolute: bool) -> str:
    return f"{value:g}" if absolute else f"{value * 100:.3g}%"


def glyph_kind_label(kind: GlyphKind) -> str:
    return STAT_LABELS[kind.stat] + ("" if kind.absolute else "%")


def glyph_grade_label(grade: GlyphGrade) -> str:
    """Ranks 1-5 only come in Uncommon, so only 6★ names its rarity."""
    return f"{grade.rank}★" + (f" {grade.rarity}" if grade.rank == 6 else "")


def gear_filter_label(gear: GearFilter, account: Account) -> str:
    """ "any", or what it keeps out: "unequipped only · locked up to 2 · not Arena Build I,
    team cb"."""
    parts = []

    if gear.unworn_only:
        parts.append("unequipped only")

    match gear.lock_level:
        case None:
            pass

        case 0:
            parts.append("unlocked only")

        case level:
            parts.append(f"locked up to {level}")

    if gear.rules:
        parts.append("not " + ", ".join(rule_label(rule, account) for rule in gear.rules))

    return " · ".join(parts) or "any"


def rule_label(rule: Rule, account: Account) -> str:
    match rule:
        case Tagged(marker=marker):
            return MARKER_LABELS.get(marker, marker)

        case GlobalPresets():
            return "Global presets"

        case Team(preset_id=preset_id):
            team = account.preset(preset_id)
            return f"team {team.name}" if team else f"team {preset_id} (gone)"


def reason_label(reason: Reason, account: Account) -> str:
    """The rule, and through whom: "Arena Build I (Arbiter)", "preset spd"."""
    match reason:
        case Held(preset_name=preset_name):
            return f"preset {preset_name}"

        case Worn(rule=rule, champion_id=champion_id):
            champion = account.champions.get(champion_id)
            label = rule_label(rule, account)
            return f"{label} ({champion.name})" if champion else label
