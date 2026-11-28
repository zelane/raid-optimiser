"""
test_slots.py - which gear slots a champion has open (`slot_unlocked`).

- `test_accessory_slots_open_with_rank_and_ascension`: the Ring with the rank, the Amulet and
  Banner only once ascended that far too
"""

from dataclasses import dataclass

from optimiser.account import slot_unlocked
from optimiser.tables import GearTables, Slot

GEAR = GearTables(
    max_level=16,
    primary={},
    ascension={},
    required_grade={Slot.RING: 4, Slot.AMULET: 5, Slot.BANNER: 6},
)


@dataclass(frozen=True)
class Ranked:
    grade: int
    ascension: int


def open_slots(grade: int, ascension: int) -> set[Slot]:
    champion = Ranked(grade, ascension)
    return {s for s in Slot if slot_unlocked(champion, s, GEAR)}  # type: ignore[arg-type]


def test_accessory_slots_open_with_rank_and_ascension() -> None:
    armour = {Slot.WEAPON, Slot.HELMET, Slot.SHIELD, Slot.GLOVES, Slot.CHEST, Slot.BOOTS}

    assert open_slots(3, 3) == armour
    assert open_slots(4, 0) == armour | {Slot.RING}
    assert open_slots(5, 4) == armour | {Slot.RING}
    assert open_slots(5, 5) == armour | {Slot.RING, Slot.AMULET}
    assert open_slots(6, 5) == armour | {Slot.RING, Slot.AMULET}
    assert open_slots(6, 6) == set(Slot)
