"""
roles.py - who would wear an accessory: champion types, what each values and which main stats
suit them, and which types each set targets. The accessory clean-up and the roll and rework
lists value a piece by the best type it suits.

The types are the user's, kept in the store (`settings`): any faction's or one faction's
only, since accessories are faction-locked. They're seeded with the standard types below and
the types of a faction's own that its champions' scaling gives (`scaling.seed_types`).

So are the set fits (`SetTable`): each set's value (a multiplier on its pieces') and the
types it doesn't target, which still count, at `SetTable.off_target` of their score. They're
seeded from the set roles and meta tiers below (`seed_set_fits`); sets the table doesn't know
are worth 1 and target every type, and so do new types every set.

- `Kind`, `ChampionType`: a type
- `TYPE_STATS`, `ACCESSORY_MAINS`, `SUPPORT_BALANCE`: what a type can weigh and suit
- `TypeKey`, `StandardType`, `SUPPORT_WEIGHTS`, `STANDARD_TYPES`: the standard types, as
  the seed has them
- `SetRole`, `SET_ROLES`, `DEFAULT_ROLE`, `ROLE_KINDS`, `Tier`, `SET_TIERS`, `NO_SET_FACTOR`:
  who wears each set and what the meta makes of it, as the seed has them
- `SetFit`, `SetTable`, `DEFAULT_FIT`, `OFF_TARGET`, `seed_set_fits`: the sets as the user
  rates them
- `LOW_VALUE_SETS`, `NO_SET`: sets apart
- `crit_amulet_exception`: the one exception to a set's targets
- `type_fits`: what each type counts for on an accessory
- `group_quota`: how many of a group to keep
"""

from dataclasses import dataclass
from enum import StrEnum

from optimiser.account import Slot, Stat


class Kind(StrEnum):
    """What Faction Wars teams need: usually three supports and two damage dealers."""

    DAMAGE = "damage"
    SUPPORT = "support"


type Mains = tuple[tuple[Slot, tuple[Stat, ...]], ...]  # the main stats that suit, per slot


@dataclass(frozen=True)
class ChampionType:
    """What a kind of champion values in an accessory, per stat, in average 6★ rolls (flat
    and % together), and the main stats that suit them. `faction` (the game's name) is set on
    a faction's own types; `champions` names who a seeded one was made from. Hashable, so
    scores can be cached."""

    key: str
    label: str
    kind: Kind
    weights: tuple[tuple[Stat, float], ...]
    mains: Mains
    faction: str | None = None
    champions: tuple[str, ...] = ()

    @property
    def balance(self) -> float:
        """Weight on the lesser of HP and DEF: supports that weigh both want them together."""
        both = self.weight(Stat.HP) and self.weight(Stat.DEF)
        return SUPPORT_BALANCE if self.kind is Kind.SUPPORT and both else 0

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
    SUPPORT_ACC = "support_acc"
    SUPPORT_RES = "support_res"


TYPE_STATS = (Stat.SPD, Stat.ATK, Stat.HP, Stat.DEF, Stat.CD, Stat.ACC, Stat.RES)
ACCESSORY_MAINS: Mains = (  # the main stats each accessory slot rolls
    (Slot.RING, (Stat.ATK, Stat.HP, Stat.DEF)),
    (Slot.AMULET, (Stat.CD, Stat.ATK, Stat.HP, Stat.DEF)),
    (Slot.BANNER, (Stat.ACC, Stat.RES, Stat.ATK, Stat.HP, Stat.DEF)),
)
SUPPORT_BALANCE = 2  # supports want HP and DEF together: this much again of the lesser one


@dataclass(frozen=True)
class StandardType:
    """A standard type as the seed has it."""

    label: str
    kind: Kind
    weights: dict[Stat, float]
    mains: Mains


# What a support wants, ACC and RES alike (a faction's own supports start from it); the
# standard supports are split by which of the two they want.
SUPPORT_WEIGHTS = {Stat.SPD: 5, Stat.ACC: 4, Stat.RES: 4, Stat.HP: 2, Stat.DEF: 2}

# Damage dealers want ACC 3: nearly all (119 of 144 non-support 6★ forms, 2026-11) place debuffs or
# take turn meter, and those that don't lose nothing by it (a piece scores as its best type).
STANDARD_TYPES: dict[TypeKey, StandardType] = {
    TypeKey.ATK_DAMAGE: StandardType(
        "ATK damage",
        Kind.DAMAGE,
        {Stat.ATK: 5, Stat.CD: 5, Stat.SPD: 4, Stat.ACC: 3, Stat.HP: 0.5, Stat.DEF: 0.5},
        (
            (Slot.RING, (Stat.ATK,)),
            (Slot.AMULET, (Stat.CD,)),
            (Slot.BANNER, (Stat.ATK, Stat.ACC)),
        ),
    ),
    TypeKey.HP_DAMAGE: StandardType(
        "HP damage",
        Kind.DAMAGE,
        {Stat.HP: 5, Stat.CD: 5, Stat.SPD: 4, Stat.ACC: 3, Stat.DEF: 0.5},
        (
            (Slot.RING, (Stat.HP,)),
            (Slot.AMULET, (Stat.CD,)),
            (Slot.BANNER, (Stat.HP, Stat.ACC)),
        ),
    ),
    TypeKey.DEF_DAMAGE: StandardType(
        "DEF damage",
        Kind.DAMAGE,
        {Stat.DEF: 5, Stat.CD: 5, Stat.SPD: 4, Stat.ACC: 3, Stat.HP: 0.5},
        (
            (Slot.RING, (Stat.DEF,)),
            (Slot.AMULET, (Stat.CD,)),
            (Slot.BANNER, (Stat.DEF, Stat.ACC)),
        ),
    ),
    # Bombs scale off ATK, and so do poisons with the Arachnelixir relic; debuffers that
    # scale off nothing wear support pieces instead.
    TypeKey.DEBUFFER: StandardType(
        "Bomber / poisoner",
        Kind.DAMAGE,
        {Stat.ACC: 5, Stat.SPD: 5, Stat.ATK: 4, Stat.HP: 1, Stat.DEF: 1},
        (
            (Slot.RING, (Stat.ATK,)),
            (Slot.AMULET, (Stat.ATK,)),
            (Slot.BANNER, (Stat.ACC, Stat.ATK)),
        ),
    ),
    TypeKey.SUPPORT_ACC: StandardType(
        "Support ACC",
        Kind.SUPPORT,
        {**SUPPORT_WEIGHTS, Stat.RES: 0},
        (
            (Slot.RING, (Stat.HP, Stat.DEF)),
            (Slot.AMULET, (Stat.HP, Stat.DEF)),
            (Slot.BANNER, (Stat.ACC, Stat.HP, Stat.DEF)),
        ),
    ),
    TypeKey.SUPPORT_RES: StandardType(
        "Support RES",
        Kind.SUPPORT,
        {**SUPPORT_WEIGHTS, Stat.ACC: 0},
        (
            (Slot.RING, (Stat.HP, Stat.DEF)),
            (Slot.AMULET, (Stat.HP, Stat.DEF)),
            (Slot.BANNER, (Stat.RES, Stat.HP, Stat.DEF)),
        ),
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


@dataclass(frozen=True)
class Tier:
    """How the meta rates a set: a multiplier on its pieces' value, and why."""

    factor: float
    reason: str


# Sets not listed are 1.
SET_TIERS = {
    66: Tier(1.3, "the top PvP set"),  # Mercurial
    59: Tier(1.3, "the only real damage set on accessories"),  # Merciless
    35: Tier(1.3, "an outstanding 9-piece bonus"),  # Swift Parry
    61: Tier(1.15, "an outstanding 1-piece bonus"),  # Feral
    60: Tier(1.15, "an outstanding 1-piece bonus"),  # Slayer
    62: Tier(1.15, "the best 2-piece speed bonus"),  # Pinpoint
}
NO_SET_FACTOR = 0.6  # set-less pieces are kept only when very good
LOW_VALUE_SETS = frozenset({NO_SET, 1002, 1004, 1001, 64, 63})  # one of each is enough

ROLE_KINDS = {
    SetRole.DAMAGE: (Kind.DAMAGE,),
    SetRole.HYBRID: (Kind.DAMAGE, Kind.SUPPORT),
    SetRole.SUPPORT: (Kind.SUPPORT,),
    SetRole.ANY: (Kind.DAMAGE, Kind.SUPPORT),
}
OFF_TARGET = 0.5  # until the user sets it
KEEP = 2  # of each group, unless `group_quota` says less


@dataclass(frozen=True)
class SetFit:
    """A set as the user rates it: what its pieces are worth against an average set's, and
    the keys of the types it doesn't target."""

    factor: float
    off: frozenset[str] = frozenset()


DEFAULT_FIT = SetFit(1.0)  # sets the table doesn't know


@dataclass(frozen=True)
class SetTable:
    """Every set's fit, and the share of its score a type counts for on a set that doesn't
    target it. Hashable, so scores can be cached."""

    fits: tuple[tuple[int, SetFit], ...]  # by set id
    off_target: float

    def fit(self, set_id: int) -> SetFit:
        return dict(self.fits).get(set_id, DEFAULT_FIT)

    def factor(self, set_id: int) -> float:
        return self.fit(set_id).factor

    def targets(self, set_id: int, champion_type: ChampionType) -> bool:
        return champion_type.key not in self.fit(set_id).off

    def kinds(self, set_id: int, types: tuple[ChampionType, ...]) -> set[Kind]:
        """The kinds of the types the set targets."""
        return {t.kind for t in types if self.targets(set_id, t)}


def seed_set_fits(types: tuple[ChampionType, ...]) -> dict[int, SetFit]:
    """From the set roles and meta tiers: a set doesn't target the types of a kind its role
    isn't worn by."""
    set_ids = sorted({*SET_ROLES, *SET_TIERS})
    return {set_id: seed_fit(set_id, types) for set_id in set_ids}


def seed_fit(set_id: int, types: tuple[ChampionType, ...]) -> SetFit:
    kinds = ROLE_KINDS[SET_ROLES.get(set_id, DEFAULT_ROLE)]
    tier = SET_TIERS.get(set_id)
    factor = NO_SET_FACTOR if set_id == NO_SET else tier.factor if tier else 1.0
    return SetFit(factor, frozenset(t.key for t in types if t.kind not in kinds))


def crit_amulet_exception(
    sets: SetTable, types: tuple[ChampionType, ...], set_id: int, slot: Slot, main: Stat
) -> bool:
    """A set that targets no damage type still keeps a C.DMG amulet, counted in full for
    damage types: some bosses' mechanics turn on crits."""
    return slot is Slot.AMULET and main is Stat.CD and Kind.DAMAGE not in sets.kinds(set_id, types)


def type_fits(
    sets: SetTable,
    types: tuple[ChampionType, ...],
    set_id: int,
    slot: Slot,
    main: Stat,
    faction: str | None,
) -> tuple[float, ...]:
    """Per type (in `types` order), the share of its score it counts for on an accessory: 0
    unless it's of everyone or the piece's faction and the main stat suits it; then 1 if the
    set targets it, else the table's `off_target`."""
    crit = crit_amulet_exception(sets, types, set_id, slot, main)

    def fit(champion_type: ChampionType) -> float:
        if champion_type.faction not in (None, faction) or not champion_type.suits(slot, main):
            return 0.0

        if sets.targets(set_id, champion_type) or (crit and champion_type.kind is Kind.DAMAGE):
            return 1.0

        return sets.off_target

    return tuple(fit(t) for t in types)


def group_quota(
    sets: SetTable, types: tuple[ChampionType, ...], set_id: int, slot: Slot, main: Stat
) -> int:
    if set_id in LOW_VALUE_SETS or crit_amulet_exception(sets, types, set_id, slot, main):
        return 1

    return KEEP
