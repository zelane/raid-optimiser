"""
cleanup.py - making room for accessories. Only unequipped gear takes inventory space; what
overflows waits in the mailbox. The plan takes the inventory and the mailbox together, keeps
what has to be kept, and drops the lowest-valued of the rest until `target_free` spaces are
left: dropped inventory pieces are sold, dropped mailbox pieces left unclaimed, the mailbox
pieces kept claimed.

The numbers are the user's (`rules.Rules`, on the assessment).

Worn pieces are often not the best of their group: where a loose piece of the same slot, main
stat, set and faction is clearly better than one an unlocked champion wears, the plan swaps
them (`find_swaps`) and plans as if done, so the piece coming off may be what's sold. A
set-less piece gives way to any set piece of its slot, main stat and faction with better
stats.

Never dropped: special variants (Corrupted: unusual stats; left alone entirely, swaps too),
pieces protected by hand, reserved pieces (`optimiser.reserve`: swaps may still move them);
and, each switched on or off in the rules: banners with SPD rolled often, each set's best RES
banners with SPD (spares for RES breakpoints, the Chimera's and Hydra's), pieces of good
potential, each faction's Faction Wars reserve (its best support pieces and best damage
pieces of each slot, worn ones included), and high-rank damage-set amulets not yet reworked
(a rework may make them C.DMG). Groups (slot, main stat, set, faction) keep the rules' quota
of pieces each (`Rules.quota`), worn ones on unlocked champions counting; pieces past that go
first, as if worth the rules' `surplus_factor` of their value.

- `ACCESSORY_SPACE`, `DEFAULT_TARGET_FREE`: the inventory
- `Keep`, `SWITCHED`, `Group`, `Placed`, `Pairing`, `Place`, `Swap`, `Plan`: the plan
- `plan_cleanup`: the workflow
- `find_swaps` (`set_upgrades`, `worn_score`), `res_speed_reserve`, `faction_wars_reserve`,
  `places_in_groups`, `keep_reasons` (`could_rework_to_crit`), `place_piece`: its steps
- `Reserves`: what the plan's own reserves keep
- `kind_score`, `group_of`, `speed_value`, `speed_rolls`: what they share
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from optimiser.accessories.assess import Assessed, Assessment, Where
from optimiser.accessories.roles import NO_SET, Kind
from optimiser.accessories.rules import Rules
from optimiser.account import Slot, Stat

ACCESSORY_SPACE = 2200
DEFAULT_TARGET_FREE = 100


class Keep(StrEnum):
    PROTECTED = "protected"
    RESERVED = "reserved"
    SPECIAL = "special variant"
    SPEED = "SPD rolled often"
    RES_SPEED = "RES/SPD banner of its set"
    POTENTIAL = "good potential"
    FACTION_WARS = "Faction Wars reserve"
    CRIT_REWORK = "could rework to C.DMG"


SWITCHED = {  # the keep rules the user may switch off, by their `Rules` switch
    Keep.SPEED: "keep_speed",
    Keep.RES_SPEED: "keep_res_speed",
    Keep.POTENTIAL: "keep_potential",
    Keep.FACTION_WARS: "keep_faction_wars",
    Keep.CRIT_REWORK: "keep_crit_rework",
}


@dataclass(frozen=True)
class Group:
    slot: Slot
    main: Stat
    set_id: int
    faction: str | None


@dataclass(frozen=True)
class Placed:
    """A loose piece (inventory or mailbox): its place in its group (1 the best), and the
    value drops go by."""

    piece: Assessed
    group: Group
    place: int
    quota: int
    order_value: float
    keep: tuple[Keep, ...]

    def surplus(self) -> bool:
        return self.place > self.quota


@dataclass(frozen=True)
class Pairing:
    """A loose piece that should replace one worn: same slot, main stat and faction."""

    better: Assessed
    worn: Assessed

    def gain(self) -> float:
        """What wearing the better piece gives over the worn one, as they are now."""
        return worn_score(self.better) - worn_score(self.worn)


@dataclass(frozen=True)
class Place:
    """A piece's place in its group (1 the best), and how many the group keeps."""

    place: int
    quota: int


@dataclass(frozen=True)
class Swap:
    """Equip the pairing's `better` (loose) on `champion_id`, in place of its `worn`: the same
    set too (so the set bonus stays) unless `worn` has none. `then_sell`: `worn`, once off, is
    among what the plan drops."""

    pairing: Pairing
    champion_id: int
    then_sell: bool


@dataclass(frozen=True)
class Plan:
    """Planned with the swaps done. `to_sell`: inventory pieces, to sell now; pieces coming
    off in swaps that go are the swaps' `then_sell`. `short`: drops still needed once
    everything that may go has gone."""

    space: int
    target_free: int
    inventory: int  # unequipped accessories, taking space
    mailbox: int
    worn: int
    kept: tuple[Placed, ...]
    to_sell: tuple[Placed, ...]
    to_claim: tuple[Placed, ...]
    leave_unclaimed: tuple[Placed, ...]
    swaps: tuple[Swap, ...]
    short: int

    def sold_after_swaps(self) -> int:
        return sum(1 for swap in self.swaps if swap.then_sell)

    def free_after(self) -> int:
        """Swaps change nothing (one piece on, one off); selling and claiming do."""
        sold = len(self.to_sell) + self.sold_after_swaps()
        return self.space - self.inventory + sold - len(self.to_claim)

    def dropped(self) -> set[int]:
        swapped_off = {s.pairing.worn.artifact.id for s in self.swaps if s.then_sell}
        return {p.piece.artifact.id for p in (*self.to_sell, *self.leave_unclaimed)} | swapped_off


def plan_cleanup(
    assessment: Assessment, protected: set[int], reserved: set[int], target_free: int
) -> Plan:
    pieces, rules = assessment.pieces, assessment.rules
    pairs = find_swaps(pieces, rules)
    going_on = {pair.better.artifact.id for pair in pairs}
    coming_off = {pair.worn.artifact.id for pair in pairs}
    loose = [
        p
        for p in pieces
        if (p.where is not Where.WORN and p.artifact.id not in going_on)
        or p.artifact.id in coming_off
    ]
    faction_wars = faction_wars_reserve(pieces, rules)
    res_speed = res_speed_reserve(assessment)
    places = places_in_groups(assessment)

    placed = [
        place_piece(
            piece,
            places[piece.artifact.id],
            rules,
            keep_reasons(piece, assessment, protected, reserved, Reserves(faction_wars, res_speed)),
        )
        for piece in loose
    ]

    capacity = ACCESSORY_SPACE - target_free
    to_drop = max(len(placed) - capacity, 0)
    dropping = sorted((p for p in placed if not p.keep), key=lambda p: p.order_value)[:to_drop]
    dropped = {p.piece.artifact.id for p in dropping}

    def dropped_from(where: Where) -> tuple[Placed, ...]:
        return tuple(p for p in dropping if p.piece.where is where)

    return Plan(
        space=ACCESSORY_SPACE,
        target_free=target_free,
        inventory=sum(1 for p in pieces if p.where is Where.INVENTORY),
        mailbox=sum(1 for p in pieces if p.where is Where.MAILBOX),
        worn=sum(1 for p in pieces if p.where is Where.WORN),
        kept=tuple(p for p in placed if p.piece.artifact.id not in dropped),
        to_sell=dropped_from(Where.INVENTORY),
        to_claim=tuple(
            p
            for p in placed
            if p.piece.where is Where.MAILBOX and p.piece.artifact.id not in dropped
        ),
        leave_unclaimed=dropped_from(Where.MAILBOX),
        swaps=tuple(
            Swap(pair, pair.worn.wearer or 0, pair.worn.artifact.id in dropped) for pair in pairs
        ),
        short=to_drop - len(dropping),
    )


def place_piece(piece: Assessed, place: Place, rules: Rules, keep: tuple[Keep, ...]) -> Placed:
    """Surplus pieces go first, as if worth `surplus_factor` of their value."""
    surplus = place.place > place.quota
    order_value = piece.value * (rules.surplus_factor if surplus else 1)
    return Placed(piece, group_of(piece), place.place, place.quota, order_value, keep)


def find_swaps(pieces: tuple[Assessed, ...], rules: Rules) -> list[Pairing]:
    """Pairs, biggest gain first: in each group, the best inventory pieces
    against the weakest worn by unlocked champions, while the loose one, as it is now, scores
    `swap_margin` times as much. Then set-less pieces still worn give way to any set piece of
    their slot, main stat and faction whose stats are better at all (`set_upgrades`)."""
    loose: dict[Group, list[Assessed]] = defaultdict(list)
    worn: dict[Group, list[Assessed]] = defaultdict(list)

    for piece in pieces:
        if piece.artifact.special():
            continue  # left alone, worn or not

        if piece.where is Where.INVENTORY:
            loose[group_of(piece)].append(piece)
        elif piece.where is Where.WORN and not piece.wearer_locked and piece.wearer is not None:
            worn[group_of(piece)].append(piece)

    pairs = []

    for group, wearing in worn.items():
        best_first = sorted(loose.get(group, ()), key=worn_score, reverse=True)
        weakest_first = sorted(wearing, key=worn_score)
        pairs += [
            Pairing(better, current)
            for better, current in zip(best_first, weakest_first, strict=False)
            if worn_score(better) > worn_score(current) * rules.swap_margin
        ]

    pairs += set_upgrades(loose, worn, pairs)
    return sorted(pairs, key=lambda pair: pair.gain(), reverse=True)


def set_upgrades(
    loose: dict[Group, list[Assessed]],
    worn: dict[Group, list[Assessed]],
    taken: list[Pairing],
) -> list[Pairing]:
    """A set piece beats a set-less one whenever its stats are better: it may add or grow a
    set bonus, and costs nothing. Each set-less piece (weakest first) takes the best loose set
    piece of its slot, main stat and faction not already swapped in."""
    used = {piece.artifact.id for pair in taken for piece in (pair.better, pair.worn)}
    pairs = []

    def same_kind(group: Group) -> tuple:
        return group.slot, group.main, group.faction

    set_pieces: dict[tuple, list[Assessed]] = defaultdict(list)

    for group, members in loose.items():
        if group.set_id != NO_SET:
            set_pieces[same_kind(group)] += members

    set_less = [p for group, ps in worn.items() if group.set_id == NO_SET for p in ps]

    for current in sorted(set_less, key=worn_score):
        if current.artifact.id in used:
            continue

        candidates = [
            p
            for p in set_pieces.get(same_kind(group_of(current)), ())
            if p.artifact.id not in used and worn_score(p) > worn_score(current)
        ]
        if not candidates:
            continue

        better = max(candidates, key=lambda p: (worn_score(p), p.set_factor))
        used |= {better.artifact.id, current.artifact.id}
        pairs.append(Pairing(better, current))

    return pairs


def worn_score(piece: Assessed) -> float:
    """What wearing it gives now: its stats as they are, not what rolling or a rework might
    make of it."""
    return piece.potential.now.best


@dataclass(frozen=True)
class Reserves:
    """The pieces the plan's own reserves keep, by artifact id."""

    faction_wars: set[int]
    res_speed: set[int]


def keep_reasons(
    piece: Assessed,
    assessment: Assessment,
    protected: set[int],
    reserved: set[int],
    reserves: Reserves,
) -> tuple[Keep, ...]:
    """The rules that keep the piece, of those switched on."""
    artifact, rules = piece.artifact, assessment.rules
    checks = (
        (Keep.PROTECTED, artifact.id in protected),
        (Keep.RESERVED, artifact.id in reserved),
        (Keep.SPECIAL, artifact.special()),
        (Keep.SPEED, artifact.slot is Slot.BANNER and speed_rolls(piece) >= rules.speed_rolls),
        (Keep.RES_SPEED, artifact.id in reserves.res_speed),
        (Keep.POTENTIAL, assessment.is_good(piece)),
        (Keep.FACTION_WARS, artifact.id in reserves.faction_wars),
        (Keep.CRIT_REWORK, could_rework_to_crit(piece, assessment)),
    )
    return tuple(
        reason
        for reason, applies in checks
        if applies and (reason not in SWITCHED or getattr(rules, SWITCHED[reason]))
    )


def could_rework_to_crit(piece: Assessed, assessment: Assessment) -> bool:
    """An amulet of a damage set (one targeting damage types only), of the rules'
    `crit_rework_rank` or up, not yet reworked: a rework may make it a C.DMG one, among the
    most valuable pieces there are. Below 6★ the main stat is too weak to be worth the gamble,
    by default."""
    artifact = piece.artifact
    return (
        artifact.slot is Slot.AMULET
        and artifact.rank >= assessment.rules.crit_rework_rank
        and not artifact.reworked
        and assessment.sets.kinds(artifact.set_id, assessment.types) == {Kind.DAMAGE}
    )


def res_speed_reserve(assessment: Assessment) -> set[int]:
    """Each set's best RES banners with SPD (most SPD rolled first, then value), as many as
    its rules' `res_speed`: an easy way to a RES breakpoint, for teams that change often.
    Worn ones count, as for the Faction Wars reserve; set-less banners aren't kept for it."""
    by_set: dict[int, list[Assessed]] = defaultdict(list)

    for piece in assessment.pieces:
        artifact = piece.artifact

        if (
            artifact.slot is Slot.BANNER
            and artifact.set_id != NO_SET
            and artifact.primary.stat is Stat.RES
            and speed_value(piece) > 0
        ):
            by_set[artifact.set_id].append(piece)

    reserve: set[int] = set()

    for set_id, banners in by_set.items():
        best = sorted(banners, key=lambda p: (speed_value(p), p.value), reverse=True)
        count = assessment.rules.set_rules(set_id).res_speed
        reserve |= {p.artifact.id for p in best[:count]}

    return reserve


def faction_wars_reserve(pieces: tuple[Assessed, ...], rules: Rules) -> set[int]:
    """Each faction's best pieces of each slot, per kind. Worn ones fill the reserve too, so
    only the loose ones it needs on top are kept for it."""
    by_shelf: dict[tuple[str, Slot], list[Assessed]] = defaultdict(list)

    for piece in pieces:
        if piece.artifact.faction is not None:
            by_shelf[(piece.artifact.faction, piece.artifact.slot)].append(piece)

    reserve: set[int] = set()

    for shelf_pieces in by_shelf.values():
        for kind, count in rules.faction_wars().items():
            scored = [(kind_score(p, kind), p) for p in shelf_pieces]
            best = sorted(scored, key=lambda entry: entry[0], reverse=True)[:count]
            reserve |= {p.artifact.id for score, p in best if score > 0}

    return reserve


def kind_score(piece: Assessed, kind: Kind) -> float:
    scores = piece.potential.natural
    return scores.support if kind is Kind.SUPPORT else scores.damage


def places_in_groups(assessment: Assessment) -> dict[int, Place]:
    """Artifact id -> its place in its group. Pieces worn by locked
    champions are left out: they aren't spare."""
    groups: dict[Group, list[Assessed]] = defaultdict(list)

    for piece in assessment.pieces:
        if not piece.wearer_locked:
            groups[group_of(piece)].append(piece)

    places = {}

    for group, members in groups.items():
        quota = assessment.rules.quota(
            assessment.sets, assessment.types, group.set_id, group.slot, group.main
        )
        ranked = sorted(members, key=lambda p: p.value, reverse=True)
        places |= {p.artifact.id: Place(place, quota) for place, p in enumerate(ranked, start=1)}

    return places


def group_of(piece: Assessed) -> Group:
    artifact = piece.artifact
    return Group(artifact.slot, artifact.primary.stat or Stat.HP, artifact.set_id, artifact.faction)


def speed_value(piece: Assessed) -> float:
    """Its SPD substat, glyph left out (0: none)."""
    return max(
        (line.value for line in piece.artifact.substats if line.stat is Stat.SPD),
        default=0,
    )


def speed_rolls(piece: Assessed) -> int:
    return max(
        (line.rolls + 1 for line in piece.artifact.substats if line.stat is Stat.SPD), default=0
    )
