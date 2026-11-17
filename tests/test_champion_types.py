"""
test_champion_types.py - the accessory champion types the store keeps (`optimiser.settings`):
seeded once, edits kept, the old per-stat weights taken over.

- `test_seeded_with_the_standard_types`: the first read seeds them, keyed by row id
- `test_seeds_only_once`: deleting every type doesn't bring them back
- `test_edits_round_trip`: a saved type reads back as saved, a new one is added
- `test_old_weights_carry_into_the_seed`: `type_weights` rows go over the defaults, then go
- `test_reseed_starts_over`: a reset brings the seed back, set fits with it, edits gone
"""

import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from optimiser.accessories.roles import STANDARD_TYPES, Kind
from optimiser.account import Account, Slot, Stat
from optimiser.settings import (
    add_champion_type,
    delete_champion_type,
    read_champion_types,
    read_set_table,
    reseed_accessories,
    save_champion_type,
    save_set_fit,
    set_off_target,
)
from optimiser.store import backup

NO_ROSTER = cast(Account, SimpleNamespace(champions={}))  # no 6★ champions: standard types only


def test_seeded_with_the_standard_types(tmp_path: Path):
    types = read_champion_types(tmp_path / "store.sqlite", NO_ROSTER)

    assert [t.label for t in types] == [it.label for it in STANDARD_TYPES.values()]
    assert all(t.key.isdigit() and t.faction is None for t in types)
    assert types[-1].kind is Kind.SUPPORT and types[-1].balance > 0


def test_seeds_only_once(tmp_path: Path):
    store = tmp_path / "store.sqlite"

    for champion_type in read_champion_types(store, NO_ROSTER):
        delete_champion_type(store, champion_type.key)

    assert read_champion_types(store, NO_ROSTER) == ()


def test_edits_round_trip(tmp_path: Path):
    store = tmp_path / "store.sqlite"
    first = read_champion_types(store, NO_ROSTER)[0]
    edited = replace(
        first,
        label="Demonspawn HP",
        faction="Demonspawn",
        weights=((Stat.SPD, 3.5), (Stat.HP, 5.0)),  # in `TYPE_STATS` order
        mains=((Slot.RING, (Stat.HP,)), (Slot.AMULET, ()), (Slot.BANNER, (Stat.HP,))),
    )
    save_champion_type(store, edited)
    added = add_champion_type(store, replace(edited, label="Copy"))

    types = {t.key: t for t in read_champion_types(store, NO_ROSTER)}

    assert types[first.key] == edited
    assert types[str(added)].label == "Copy" and types[str(added)].faction == "Demonspawn"


def test_old_weights_carry_into_the_seed(tmp_path: Path):
    store = tmp_path / "store.sqlite"

    with sqlite3.connect(store) as db:
        db.execute("CREATE TABLE type_weights (type TEXT, stat TEXT, weight REAL)")
        db.execute("INSERT INTO type_weights VALUES ('atk_damage', 'Resistance', 2)")
        db.execute("INSERT INTO type_weights VALUES ('atk_damage', 'Accuracy', 0)")

    atk = read_champion_types(store, NO_ROSTER)[0]

    assert atk.weight(Stat.RES) == 2 and atk.weight(Stat.ACC) == 0
    assert atk.weight(Stat.ATK) == 5

    with sqlite3.connect(store) as db:
        tables = {name for (name,) in db.execute("SELECT name FROM sqlite_master")}

    assert "type_weights" not in tables


def test_reseed_starts_over(tmp_path: Path):
    store = tmp_path / "store.sqlite"
    seeded = read_champion_types(store, NO_ROSTER)
    sets = read_set_table(store, seeded)
    delete_champion_type(store, seeded[0].key)
    set_id, fit = sets.fits[0]
    save_set_fit(store, set_id, replace(fit, factor=9.0))
    set_off_target(store, 0.25)
    backup(store, tmp_path / "copy.sqlite")

    types, table = reseed_accessories(store, NO_ROSTER)

    assert [t.label for t in types] == [t.label for t in seeded]
    assert table.factor(set_id) == fit.factor and table.off_target == 0.25
    assert set().union(*(f.off for _, f in table.fits)) <= {t.key for t in types}
    assert len(read_champion_types(tmp_path / "copy.sqlite", NO_ROSTER)) == len(seeded) - 1
