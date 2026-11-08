"""
settings.py - what the user has set, read from the store as the model's types and written
back by the store's names: the assumptions solves make (flags and glyphs) and the standard
champion types' weights. The only part of the optimiser besides the store that touches the
file; the model takes what this returns.

- `read_assumptions`, `set_flag`: what solves assume
- `read_planned`, `plan_glyph`: the glyphs assumed on gear
- `read_standard_types`, `set_type_weight`: the standard types, with the stored weights
"""

from pathlib import Path

from optimiser.accessories.roles import ChampionType, TypeKey, standard_types
from optimiser.account import Account, GlyphGrade, GlyphKind, Stat, Tables
from optimiser.assume import Assumptions, Flag
from optimiser.glyphs import grade_key, kind_key, parse_grade, parse_kind
from optimiser.store import (
    read_flags,
    read_glyphs,
    read_weights,
    write_flag,
    write_glyph,
    write_weight,
)


def read_assumptions(store: Path, account: Account) -> Assumptions:
    flags = frozenset(Flag(name) for name in read_flags(store) if name in Flag)
    return Assumptions(flags, read_planned(store, account.tables))


def set_flag(store: Path, flag: Flag, on: bool) -> None:
    write_flag(store, flag, on)


def read_planned(store: Path, tables: Tables) -> dict[GlyphKind, GlyphGrade]:
    """What the store holds, less anything the game's glyph table no longer has."""
    planned = {}

    for kind_text, grade_text in read_glyphs(store).items():
        kind, grade = parse_kind(kind_text), parse_grade(grade_text)
        if kind and grade and grade in tables.glyphs.get(kind, {}):
            planned[kind] = grade

    return planned


def plan_glyph(store: Path, kind: GlyphKind, grade: GlyphGrade | None) -> None:
    """None stops assuming the kind."""
    write_glyph(store, kind_key(kind), grade_key(grade) if grade else None)


def read_standard_types(store: Path) -> tuple[ChampionType, ...]:
    """Stored weights for types or stats that no longer exist are ignored."""
    stored: dict[TypeKey, dict[Stat, float]] = {}

    for (type_name, stat), weight in read_weights(store).items():
        if type_name in TypeKey and stat in Stat:
            stored.setdefault(TypeKey(type_name), {})[Stat(stat)] = weight

    return standard_types(stored)


def set_type_weight(store: Path, key: TypeKey, stat: Stat, weight: float) -> None:
    write_weight(store, (key.value, stat.value), weight)
