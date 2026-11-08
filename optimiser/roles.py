"""
roles.py - who would wear an accessory: champion types, what each values and which main stats
suit them, and which types each set is worn by. The accessory clean-up and the roll and rework
lists value a piece by the best type it suits.

There are standard types for every faction (their weights editable, kept in the store) and
types of a faction's own, made from what its champions scale off (`optimiser.scaling`).

- `Kind`, `ChampionType`: a type
- `TypeKey`, `TYPE_LABELS`, `TYPE_KINDS`, `DEFAULT_TYPE_WEIGHTS`, `TYPE_MAINS`, `TYPE_STATS`,
  `SUPPORT_BALANCE`: the standard types
- `SetRole`, `SET_ROLES`, `DEFAULT_ROLE`, `LOW_VALUE_SETS`, `NO_SET`, `ROLE_KINDS`: who wears
  each set
- `SET_TIERS`, `NO_SET_FACTOR`, `set_factor`: what the meta makes of each set
- `standard_types`, `read_standard_types`, `set_type_weight`: the standard types, with the
  store's weights
- `types_for`: the types an accessory could be for
- `group_quota`: how many of a group to keep
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from optimiser.account import Slot, Stat
from optimiser.store import read_weights, write_weight


class Kind(StrEnum):
    """What Faction Wars teams need: usually three supports and two damage dealers."""

    DAMAGE = "damage"
    SUPPORT = "support"


type Mains = tuple[tuple[Slot, tuple[Stat, ...]], ...]  # the main stats that suit, per slot


@dataclass(frozen=True)
class ChampionType:
    """What a kind of champion values in an accessory, per stat, in average 6★ rolls (flat
    and % together), and the main stats that suit them. `faction` is set on a faction's own
    types (`champions` names who it's made from). Hashable, so scores can be cached."""

    key: str
    label: str
    kind: Kind
    weights: tuple[tuple[Stat, float], ...]
    mains: Mains
    balance: float = 0  # weight on the lesser of HP and DEF, for supports
    faction: str | None = None
    champions: tuple[str, ...] = ()

    def weight(self, stat: Stat) -> float:
        return dict(self.weights).get(stat, 0)

    def suits(self, slot: Slot, main: Stat) -> bool:
        return main in dict(self.mains).get(slot, ())


class TypeKey(StrEnum):
    """As the store names them."""

    ATK_DAMAGE = "atk_damage"
    HP_DAMAGE = "hp_damage"
    DEF_DAMAGE = "def_damage"
    DEBUFFER = "debuffer"
    SUPPORT = "support"


TYPE_LABELS = {
    TypeKey.ATK_DAMAGE: "ATK damage",
    TypeKey.HP_DAMAGE: "HP damage",
    TypeKey.DEF_DAMAGE: "DEF damage",
    TypeKey.DEBUFFER: "Bomber / poisoner",
    TypeKey.SUPPORT: "Support",
}
TYPE_KINDS = {
    TypeKey.ATK_DAMAGE: Kind.DAMAGE,
    TypeKey.HP_DAMAGE: Kind.DAMAGE,
    TypeKey.DEF_DAMAGE: Kind.DAMAGE,
    TypeKey.DEBUFFER: Kind.DAMAGE,
    TypeKey.SUPPORT: Kind.SUPPORT,
}
TYPE_STATS = (Stat.SPD, Stat.ATK, Stat.HP, Stat.DEF, Stat.CD, Stat.ACC, Stat.RES)
SUPPORT_BALANCE = 2  # supports want HP and DEF together: this much again of the lesser one

DEFAULT_TYPE_WEIGHTS: dict[TypeKey, dict[Stat, float]] = {
    TypeKey.ATK_DAMAGE: {
        Stat.ATK: 5,
        Stat.CD: 5,
        Stat.SPD: 4,
        Stat.ACC: 1,
        Stat.HP: 0.5,
        Stat.DEF: 0.5,
    },
    TypeKey.HP_DAMAGE: {Stat.HP: 5, Stat.CD: 5, Stat.SPD: 4, Stat.ACC: 1, Stat.DEF: 0.5},
    TypeKey.DEF_DAMAGE: {Stat.DEF: 5, Stat.CD: 5, Stat.SPD: 4, Stat.ACC: 1, Stat.HP: 0.5},
    # Bombs scale off ATK, and so do poisons with the Arachnelixir relic; debuffers that
    # scale off nothing wear support pieces instead.
    TypeKey.DEBUFFER: {Stat.ACC: 5, Stat.SPD: 5, Stat.ATK: 4, Stat.HP: 1, Stat.DEF: 1},
    # ACC and RES alike: a banner's main stat for supports is one or the other.
    TypeKey.SUPPORT: {Stat.SPD: 5, Stat.ACC: 4, Stat.RES: 4, Stat.HP: 2, Stat.DEF: 2},
}

TYPE_MAINS: dict[TypeKey, Mains] = {
    TypeKey.ATK_DAMAGE: (
        (Slot.RING, (Stat.ATK,)),
        (Slot.AMULET, (Stat.CD,)),
        (Slot.BANNER, (Stat.ATK, Stat.ACC)),
    ),
    TypeKey.HP_DAMAGE: (
        (Slot.RING, (Stat.HP,)),
        (Slot.AMULET, (Stat.CD,)),
        (Slot.BANNER, (Stat.HP, Stat.ACC)),
    ),
    TypeKey.DEF_DAMAGE: (
        (Slot.RING, (Stat.DEF,)),
        (Slot.AMULET, (Stat.CD,)),
        (Slot.BANNER, (Stat.DEF, Stat.ACC)),
    ),
    TypeKey.DEBUFFER: (
        (Slot.RING, (Stat.ATK,)),
        (Slot.AMULET, (Stat.ATK,)),
        (Slot.BANNER, (Stat.ACC, Stat.ATK)),
    ),
    TypeKey.SUPPORT: (
        (Slot.RING, (Stat.HP, Stat.DEF)),
        (Slot.AMULET, (Stat.HP, Stat.DEF)),
        (Slot.BANNER, (Stat.ACC, Stat.RES, Stat.HP, Stat.DEF)),
    ),
}


class SetRole(StrEnum):
    DAMAGE = "Damage"
    HYBRID = "Hybrid"
    SUPPORT = "Support"
    ANY = "Any"  # no role of its own: whoever it suits


NO_SET = 0
SET_ROLES = {
    NO_SET: SetRole.ANY,
    66: SetRole.HYBRID,  # Mercurial
    47: SetRole.SUPPORT,  # Protection
    48: SetRole.HYBRID,  # Stone Skin
    62: SetRole.SUPPORT,  # Pinpoint
    65: SetRole.HYBRID,  # Chronophage
    61: SetRole.HYBRID,  # Feral
    59: SetRole.DAMAGE,  # Merciless
    58: SetRole.SUPPORT,  # Supersonic
    60: SetRole.DAMAGE,  # Slayer
    1003: SetRole.HYBRID,  # Reaction
    1002: SetRole.ANY,  # Bloodshield
    36: SetRole.SUPPORT,  # Deflection
    35: SetRole.DAMAGE,  # Swift Parry
    1000: SetRole.SUPPORT,  # Refresh
    1004: SetRole.ANY,  # Revenge
    1001: SetRole.ANY,  # Cleansing
    64: SetRole.SUPPORT,  # Rebirth
    63: SetRole.DAMAGE,  # Stonecleaver
}
DEFAULT_ROLE = SetRole.HYBRID  # sets released since

# How the meta rates a set, as a multiplier on its pieces' value; sets not listed are 1.
SET_TIERS = {
    66: (1.3, "the top PvP set"),  # Mercurial
    59: (1.3, "the only real damage set on accessories"),  # Merciless
    35: (1.3, "an outstanding 9-piece bonus"),  # Swift Parry
    61: (1.15, "an outstanding 1-piece bonus"),  # Feral
    60: (1.15, "an outstanding 1-piece bonus"),  # Slayer
    62: (1.15, "the best 2-piece speed bonus"),  # Pinpoint
}
NO_SET_FACTOR = 0.6  # set-less pieces are kept only when very good
LOW_VALUE_SETS = frozenset({NO_SET, 1002, 1004, 1001, 64, 63})  # one of each is enough

ROLE_KINDS = {
    SetRole.DAMAGE: (Kind.DAMAGE,),
    SetRole.HYBRID: (Kind.DAMAGE, Kind.SUPPORT),
    SetRole.SUPPORT: (Kind.SUPPORT,),
    SetRole.ANY: (Kind.DAMAGE, Kind.SUPPORT),
}
KEEP = 2  # of each group, unless `group_quota` says less


def set_factor(set_id: int) -> float:
    """What a set's pieces are worth against an average set's: its meta tier, or the
    set-less discount."""
    if set_id == NO_SET:
        return NO_SET_FACTOR

    return SET_TIERS.get(set_id, (1.0, ""))[0]


def standard_types(stored: dict[TypeKey, dict[Stat, float]]) -> tuple[ChampionType, ...]:
    """The default weights, with the stored ones over them."""
    return tuple(
        ChampionType(
            key=key.value,
            label=TYPE_LABELS[key],
            kind=TYPE_KINDS[key],
            weights=tuple({**DEFAULT_TYPE_WEIGHTS[key], **stored.get(key, {})}.items()),
            mains=TYPE_MAINS[key],
            balance=SUPPORT_BALANCE if key is TypeKey.SUPPORT else 0,
        )
        for key in TypeKey
    )


def read_standard_types(store: Path) -> tuple[ChampionType, ...]:
    stored: dict[TypeKey, dict[Stat, float]] = {}

    for (type_name, stat), weight in read_weights(store).items():
        if type_name in TypeKey and stat in Stat:
            stored.setdefault(TypeKey(type_name), {})[Stat(stat)] = weight

    return standard_types(stored)


def set_type_weight(store: Path, key: TypeKey, stat: Stat, weight: float) -> None:
    write_weight(store, (key.value, stat.value), weight)


def types_for(
    set_id: int, slot: Slot, main: Stat, faction: str | None, types: tuple[ChampionType, ...]
) -> tuple[str, ...]:
    """Keys of the types the set is worn by, of everyone or the piece's faction, whose main
    stats include this one. Support sets still keep a C.DMG amulet: some bosses' mechanics
    turn on crits."""
    role = SET_ROLES.get(set_id, DEFAULT_ROLE)
    kinds = ROLE_KINDS[role]

    if role is SetRole.SUPPORT and slot is Slot.AMULET and main is Stat.CD:
        kinds = (Kind.DAMAGE,)

    return tuple(
        t.key
        for t in types
        if t.kind in kinds and t.faction in (None, faction) and t.suits(slot, main)
    )


def group_quota(set_id: int, slot: Slot, main: Stat) -> int:
    role = SET_ROLES.get(set_id, DEFAULT_ROLE)

    if set_id in LOW_VALUE_SETS:
        return 1

    if role is SetRole.SUPPORT and slot is Slot.AMULET and main is Stat.CD:
        return 1

    return KEEP
