"""
settings.py - what the user has set, read from the store as the model's types and written
back by the store's names: the assumptions solves make (flags and glyphs), the champion types
and set fits accessories are valued by, and the rules that reserve gear. The only part of the
optimiser besides the store that touches the file; the model takes what this returns.

- `read_assumptions`, `set_flag`: what solves assume
- `read_planned`, `plan_glyph`: the glyphs assumed on gear
- `read_champion_types`, `add_champion_type`, `save_champion_type`, `delete_champion_type`:
  the champion types, seeded on first read (`type_record`, `parse_type`)
- `OFF_TARGET_NAME`, `read_set_table`, `save_set_fit`, `set_off_target`: the set fits,
  seeded on first read (`fit_record`, `parse_fit`)
- `read_reserve_rules`, `set_reserve_rule`: what reserves gear
"""

from pathlib import Path

from optimiser.accessories.roles import (
    OFF_TARGET,
    TYPE_STATS,
    ChampionType,
    Kind,
    SetFit,
    SetTable,
    TypeKey,
    seed_set_fits,
)
from optimiser.accessories.scaling import seed_types
from optimiser.account import Account, GlyphGrade, GlyphKind, Slot, Stat, Tables
from optimiser.assume import Assumptions, Flag
from optimiser.glyphs import grade_key, kind_key, parse_grade, parse_kind
from optimiser.reserve import Rule, parse_rule, rule_key
from optimiser.store import (
    add_type,
    delete_type,
    read_flags,
    read_glyphs,
    read_number,
    read_old_weights,
    read_set_fits,
    read_types,
    write_flag,
    write_glyph,
    write_number,
    write_reserve_rule,
    write_set_fit,
    write_type,
)
from optimiser.store import read_reserve_rules as read_rule_keys
from optimiser.store import seed_set_fits as seed_fits_store
from optimiser.store import seed_types as seed_store

OFF_TARGET_NAME = "off_target"  # the store's number for `SetTable.off_target`


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


def read_champion_types(store: Path, account: Account) -> tuple[ChampionType, ...]:
    """Seeded from the standard types and `account`'s roster the first time; records that no
    longer parse are left out."""
    if (records := read_types(store)) is None:
        edited: dict[TypeKey, dict[Stat, float]] = {}

        for (type_name, stat), weight in read_old_weights(store).items():
            if type_name in TypeKey and stat in Stat:
                edited.setdefault(TypeKey(type_name), {})[Stat(stat)] = weight

        seed_store(store, [type_record(t) for t in seed_types(account, edited)])
        records = read_types(store) or {}

    return tuple(t for type_id, record in records.items() if (t := parse_type(type_id, record)))


def add_champion_type(store: Path, champion_type: ChampionType) -> int:
    """Its key is ignored: the new type's id is returned."""
    return add_type(store, type_record(champion_type))


def save_champion_type(store: Path, champion_type: ChampionType) -> None:
    write_type(store, int(champion_type.key), type_record(champion_type))


def delete_champion_type(store: Path, key: str) -> None:
    delete_type(store, int(key))


def type_record(champion_type: ChampionType) -> dict:
    return {
        "label": champion_type.label,
        "kind": champion_type.kind.value,
        "faction": champion_type.faction,
        "weights": {stat.value: weight for stat, weight in champion_type.weights},
        "mains": {
            slot.value: [stat.value for stat in stats] for slot, stats in champion_type.mains
        },
        "champions": list(champion_type.champions),
    }


def parse_type(type_id: int, record: dict) -> ChampionType | None:
    """Keyed by its id; unknown stats and slots are dropped, None if the kind is unknown."""
    if record.get("kind") not in Kind:
        return None

    weights = record.get("weights", {})
    slots = {slot.value: slot for slot in Slot}
    return ChampionType(
        key=str(type_id),
        label=record.get("label", ""),
        kind=Kind(record["kind"]),
        weights=tuple(
            (stat, float(weights[stat.value])) for stat in TYPE_STATS if weights.get(stat.value)
        ),
        mains=tuple(
            (slots[slot], tuple(Stat(stat) for stat in stats if stat in Stat))
            for slot, stats in record.get("mains", {}).items()
            if slot in slots
        ),
        faction=record.get("faction"),
        champions=tuple(record.get("champions", ())),
    )


def read_set_table(store: Path, types: tuple[ChampionType, ...]) -> SetTable:
    """Seeded from the set roles and tiers, against `types`, the first time; records that no
    longer parse are left out (their sets then fit as unknown ones do)."""
    if (records := read_set_fits(store)) is None:
        seed = seed_set_fits(types)
        seed_fits_store(store, {set_id: fit_record(fit) for set_id, fit in seed.items()})
        records = read_set_fits(store) or {}

    stored = read_number(store, OFF_TARGET_NAME)
    fits = tuple((set_id, fit) for set_id, record in records.items() if (fit := parse_fit(record)))
    return SetTable(fits, OFF_TARGET if stored is None else stored)


def save_set_fit(store: Path, set_id: int, fit: SetFit) -> None:
    write_set_fit(store, set_id, fit_record(fit))


def set_off_target(store: Path, share: float) -> None:
    write_number(store, OFF_TARGET_NAME, share)


def fit_record(fit: SetFit) -> dict:
    return {"factor": fit.factor, "off": sorted(fit.off, key=int)}


def parse_fit(record: dict) -> SetFit | None:
    factor = record.get("factor")

    if not isinstance(factor, int | float):
        return None

    return SetFit(float(factor), frozenset(str(key) for key in record.get("off", ())))


def read_reserve_rules(store: Path) -> tuple[Rule, ...]:
    """In the order they were added; keys no longer understood are ignored."""
    return tuple(rule for key in read_rule_keys(store) if (rule := parse_rule(key)))


def set_reserve_rule(store: Path, rule: Rule, on: bool) -> None:
    write_reserve_rule(store, rule_key(rule), on)
