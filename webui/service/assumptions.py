"""
assumptions.py - the assumptions page: what solves assume (top levels, full ascension,
glyphs), kept in the store.

- `FlagView`, `GlyphChoice`, `GlyphRow`, `AssumptionsPage`: the views
- `assumptions_page`, `set_assumption`, `plan_glyph_for`: what the page asks for
- `flag_view`, `glyph_row`: what they share
"""

from dataclasses import dataclass

from optimiser.account import Account, GlyphGrade, GlyphKind
from optimiser.assume import FLAG_LABELS, Flag
from optimiser.glyphs import grade_key, kind_key
from optimiser.labels import glyph_grade_label, glyph_kind_label, line_amount
from optimiser.paths import STORE
from optimiser.settings import plan_glyph, read_assumptions, set_flag


@dataclass(frozen=True)
class FlagView:
    name: str
    label: str
    on: bool


@dataclass(frozen=True)
class GlyphChoice:
    key: str  # `grade_key`; "" for none
    label: str  # "6★ Legendary (+12)"


@dataclass(frozen=True)
class GlyphRow:
    """A glyph kind and the grade assumed for it ("" for none)."""

    key: str  # `kind_key`
    label: str
    choices: list[GlyphChoice]
    chosen: str


@dataclass(frozen=True)
class AssumptionsPage:
    flags: list[FlagView]
    glyphs: list[GlyphRow]


def assumptions_page(account: Account) -> AssumptionsPage:
    assumptions = read_assumptions(STORE, account)
    planned = assumptions.glyphs
    return AssumptionsPage(
        flags=[flag_view(flag, flag in assumptions.flags) for flag in Flag],
        glyphs=[glyph_row(account, kind, planned.get(kind)) for kind in account.tables.glyphs],
    )


def set_assumption(flag: Flag, on: bool) -> FlagView:
    set_flag(STORE, flag, on)
    return flag_view(flag, on)


def plan_glyph_for(account: Account, kind: GlyphKind, grade: GlyphGrade | None) -> GlyphRow:
    """None stops assuming the kind."""
    plan_glyph(STORE, kind, grade)
    return glyph_row(account, kind, grade)


def flag_view(flag: Flag, on: bool) -> FlagView:
    return FlagView(flag.value, FLAG_LABELS[flag], on)


def glyph_row(account: Account, kind: GlyphKind, chosen: GlyphGrade | None) -> GlyphRow:
    tops = account.tables.glyphs[kind]
    choices = [
        GlyphChoice(
            grade_key(grade), f"{glyph_grade_label(grade)} (+{line_amount(top, kind.absolute)})"
        )
        for grade, top in reversed(tops.items())
    ]
    return GlyphRow(
        key=kind_key(kind),
        label=glyph_kind_label(kind),
        choices=[GlyphChoice("", "None"), *choices],
        chosen=grade_key(chosen) if chosen else "",
    )
