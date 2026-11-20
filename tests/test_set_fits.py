"""
test_set_fits.py - the accessory sets as the user rates them (`optimiser.settings`,
`roles.type_fits`): seeded once from the set roles and tiers, edits kept, off-target types
counting for less.

- `test_seeded_from_the_roles_and_tiers`: support sets don't target damage types; tiers kept
- `test_edits_round_trip`: a saved fit and the off-target share read back as saved
- `test_fits_by_target_faction_and_main`: 1 on target, the share off it, 0 if unsuited
- `test_crit_amulet_on_a_support_set`: counts in full for damage types
"""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from optimiser.accessories.roles import NO_SET, Group, Kind, SetFit, type_fits
from optimiser.account import Account, Slot, Stat
from optimiser.settings import (
    read_champion_types,
    read_rules,
    read_set_table,
    save_set,
    set_off_target,
)

NO_ROSTER = cast(Account, SimpleNamespace(champions={}))  # no 6★ champions: standard types only
PROTECTION, MERCILESS, MERCURIAL = 47, 59, 66


def test_seeded_from_the_roles_and_tiers(tmp_path: Path):
    store = tmp_path / "store.sqlite"
    types = read_champion_types(store, NO_ROSTER)
    sets = read_set_table(store, types)

    damage = {t.key for t in types if t.kind is Kind.DAMAGE}
    assert sets.fit(PROTECTION).off == damage
    assert sets.fit(MERCURIAL).off == frozenset()
    assert sets.factor(MERCILESS) == 1.3 and sets.factor(NO_SET) == 0.6
    assert sets.fit(12345) == SetFit(1.0)  # a set released since


def test_edits_round_trip(tmp_path: Path):
    store = tmp_path / "store.sqlite"
    types = read_champion_types(store, NO_ROSTER)
    sets = read_set_table(store, types)
    rules = read_rules(store, types, sets).set_rules(PROTECTION)

    save_set(store, PROTECTION, SetFit(1.2, frozenset({types[0].key})), rules)
    set_off_target(store, 0.25)
    sets = read_set_table(store, types)

    assert sets.fit(PROTECTION) == SetFit(1.2, frozenset({types[0].key}))
    assert sets.off_target == 0.25


def test_fits_by_target_faction_and_main(tmp_path: Path):
    store = tmp_path / "store.sqlite"
    types = read_champion_types(store, NO_ROSTER)
    atk = next(t for t in types if t.label == "ATK damage")
    demonspawn = replace(atk, key="99", faction="Demonspawn")
    types = (atk, demonspawn)
    sets = replace(read_set_table(store, types), off_target=0.4)

    on_damage_set = type_fits(sets, types, Group(Slot.RING, Stat.ATK, MERCILESS, None))
    off_support_set = type_fits(
        sets, types, Group(Slot.RING, Stat.ATK, PROTECTION, "Demonspawn")
    )
    unsuited_main = type_fits(sets, types, Group(Slot.RING, Stat.HP, MERCILESS, None))

    assert on_damage_set == (1.0, 0.0)  # the Demonspawn type isn't for a faction-less piece
    assert off_support_set == (0.4, 0.4)  # a support set targets neither damage type
    assert unsuited_main == (0.0, 0.0)


def test_crit_amulet_on_a_support_set(tmp_path: Path):
    store = tmp_path / "store.sqlite"
    types = read_champion_types(store, NO_ROSTER)
    sets = read_set_table(store, types)
    atk = [t.kind is Kind.DAMAGE and t.suits(Slot.AMULET, Stat.CD) for t in types]

    fits = type_fits(sets, types, Group(Slot.AMULET, Stat.CD, PROTECTION, None))

    assert [fit == 1.0 for fit in fits] == atk
