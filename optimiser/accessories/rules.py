"""
rules.py - the user's rules for valuing and keeping accessories: what good is and what being
short of good pieces is worth (`assess`), what the clean-up always keeps and how many of a
group (`cleanup`), and when a swap or a rework is worth it (`cleanup`, `enhance`). Scoring
itself (`potential`) reads none of them, so changing one rescores nothing.

Each set has its own: how many pieces of each of its groups (slot, main stat, set, faction)
to keep, and how many RES banners with SPD. They're kept with the set's fit and seeded from
the rules below (`seed_set_rules`): low-value sets keep one of each group, the rest two; a
set targeting any support type keeps two RES/SPD banners, else one. Sets the table doesn't
know take `DEFAULT_SET_RULES`.

The keep rules that aren't the user's own doing (protected, reserved, special variants) can't
be switched off; the rest can.

- `SetRules`, `DEFAULT_SET_RULES`: a set's
- `KEEP`, `LOW_VALUE_SETS`, `RES_SPEED`, `seed_set_rules`: what they're seeded from
- `Rules`, `DEFAULT_RULES`: everything else, as the code has it until the user sets it
- `RuleBounds`, `RULE_BOUNDS`, `SET_RULE_BOUNDS`, `rule_bounds`: what each number may be
"""

from dataclasses import dataclass, fields

from optimiser.accessories.roles import (
    NO_SET,
    ChampionType,
    Group,
    Kind,
    SetTable,
    crit_amulet_exception,
)


@dataclass(frozen=True)
class SetRules:
    """`keep`: pieces of each of the set's groups; `res_speed`: its best RES banners with SPD
    (spares for RES breakpoints, the Chimera's and Hydra's)."""

    keep: int
    res_speed: int


KEEP = 2
LOW_VALUE_SETS = frozenset({NO_SET, 1002, 1004, 1001, 64, 63})  # one of each group is enough
RES_SPEED = {Kind.SUPPORT: 2, Kind.DAMAGE: 1}  # by whether the set targets a support type
DEFAULT_SET_RULES = SetRules(KEEP, RES_SPEED[Kind.SUPPORT])  # unknown sets target every type


def seed_set_rules(set_id: int, sets: SetTable, types: tuple[ChampionType, ...]) -> SetRules:
    support = Kind.SUPPORT in sets.kinds(set_id, types)
    return SetRules(
        1 if set_id in LOW_VALUE_SETS else KEEP,
        RES_SPEED[Kind.SUPPORT if support else Kind.DAMAGE],
    )


@dataclass(frozen=True)
class Rules:
    """`keep_*`: whether that keep rule holds. Shortage: a shelf's (set, faction, slot) good
    pieces raise or lower each of its pieces' value, by how many there are (`scarcity`). A
    group's pieces past its quota go first, as if worth `surplus_factor` of their value. A
    loose piece replaces a worn one when it scores `swap_margin` times as much; a rework is
    listed when it beats the piece by `rework_margin`."""

    keep_speed: bool = True
    speed_rolls: int = 3  # a banner's SPD rolled this often (the first roll included)
    keep_res_speed: bool = True  # each set's `SetRules.res_speed`
    keep_potential: bool = True
    good_share: float = 0.25  # good: in its slot's top quarter by potential
    keep_faction_wars: bool = True  # each faction's best of each slot, per kind
    faction_wars_support: int = 3
    faction_wars_damage: int = 2
    keep_crit_rework: bool = True  # unreworked amulets of damage sets, of this rank and up
    crit_rework_rank: int = 6
    crit_amulet_keep: int = 1  # a non-damage set's C.DMG amulets, of each group
    scarcity_none: float = 1.15
    scarcity_one: float = 1.05
    scarcity_two: float = 1.0
    scarcity_plenty: float = 0.9  # three or more
    surplus_factor: float = 0.75
    swap_margin: float = 1.1
    rework_margin: float = 1.1
    sets: tuple[tuple[int, SetRules], ...] = ()  # by set id

    def set_rules(self, set_id: int) -> SetRules:
        return dict(self.sets).get(set_id, DEFAULT_SET_RULES)

    def scarcity(self, good: int) -> float:
        """By the good pieces on a shelf."""
        by_count = (self.scarcity_none, self.scarcity_one, self.scarcity_two)
        return by_count[good] if good < len(by_count) else self.scarcity_plenty

    def faction_wars(self) -> dict[Kind, int]:
        """Per faction and slot."""
        return {Kind.SUPPORT: self.faction_wars_support, Kind.DAMAGE: self.faction_wars_damage}

    def quota(self, sets: SetTable, types: tuple[ChampionType, ...], group: Group) -> int:
        """How many of a group to keep."""
        if crit_amulet_exception(sets, types, group):
            return self.crit_amulet_keep

        return self.set_rules(group.set_id).keep


DEFAULT_RULES = Rules()


@dataclass(frozen=True)
class RuleBounds:
    low: float
    high: float
    whole: bool = False


RULE_BOUNDS = {
    "speed_rolls": RuleBounds(1, 6, whole=True),
    "good_share": RuleBounds(0, 1),
    "faction_wars_support": RuleBounds(0, 10, whole=True),
    "faction_wars_damage": RuleBounds(0, 10, whole=True),
    "crit_rework_rank": RuleBounds(1, 6, whole=True),
    "crit_amulet_keep": RuleBounds(0, 10, whole=True),
    "scarcity_none": RuleBounds(0, 3),
    "scarcity_one": RuleBounds(0, 3),
    "scarcity_two": RuleBounds(0, 3),
    "scarcity_plenty": RuleBounds(0, 3),
    "surplus_factor": RuleBounds(0, 1),
    "swap_margin": RuleBounds(1, 3),
    "rework_margin": RuleBounds(1, 3),
}
SET_RULE_BOUNDS = {
    "keep": RuleBounds(0, 20, whole=True),
    "res_speed": RuleBounds(0, 10, whole=True),
}


def rule_bounds() -> dict[str, RuleBounds | None]:
    """Every rule but the sets' by name: a number's bounds, None for a switch."""
    names = (f.name for f in fields(Rules) if f.name != "sets")
    return {
        name: None if isinstance(getattr(DEFAULT_RULES, name), bool) else RULE_BOUNDS[name]
        for name in names
    }
