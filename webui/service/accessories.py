"""
accessories.py - the accessories pages: swaps, the roll and rework lists, the clean-up, and
the champion types and set fits. Scoring every accessory's potential is the slow part, so
the potentials are cached per snapshot, types and set fits (not locks), and kept on disk per
piece (`scores`).

- `WeightCell`, `MainOption`, `MainsCell`, `TypeRow`, `SetColumn`, `TargetRow`,
  `TargetGroup`, `SetGrid`, `WeightTable`,
  `AccessoryRow`,
  `DropRow`, `CandidateRow`, `SwapRow`, `SwapGroup`, `SetSummary`, `CleanupView`,
  `EnhanceView`, `AccessoriesPage`, `RowContext`: the views
- `ACCESSORY_TABS`, `ENHANCE_SHOWN`, `TARGET_FREE`, `TARGET_LABELS`: their shape
- `accessories_page`, `set_target_free`, `protect_accessory`,
  `save_type`, `add_type`, `copy_type`, `delete_type`, `save_set_value`, `save_set_target`,
  `save_off_target`,
  `pieces_to_sell`: what the pages ask for
- `current_types`, `current_sets`, `current_assessment` (`potentials_for`, cached),
  `current_plan`, `current_target_free`: the state they're made from
- `cleanup_view`, `enhance_view`, `weight_table` (`set_grid`, `listed_sets`), `set_summaries`,
  `targets_label`,
  `swap_groups`, `swap_row`, `drop_row`, `row_context`, `accessory_row`, `type_labels`,
  `find_type`, `type_factions`, `ordinal`: what they share
"""

from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache

from optimiser.accessories.assess import Assessed, Assessment, assess_accessories, potentials_of
from optimiser.accessories.cleanup import DEFAULT_TARGET_FREE, Placed, Plan, Swap, plan_cleanup
from optimiser.accessories.enhance import Candidate, finish_list, rework_list, roll_list
from optimiser.accessories.potential import ACCESSORIES, Piece, Potential, Scorer, make_scorer
from optimiser.accessories.roles import (
    ACCESSORY_MAINS,
    TYPE_STATS,
    ChampionType,
    Kind,
    SetTable,
)
from optimiser.account import Account, Champion, faction_label
from optimiser.labels import STAT_LABELS
from optimiser.paths import POTENTIALS, STORE
from optimiser.reserve import Reservations, reservations
from optimiser.settings import (
    add_champion_type,
    delete_champion_type,
    read_champion_types,
    read_set_table,
    save_champion_type,
    save_set_fit,
    set_off_target,
)
from optimiser.store import read_number, read_protected, write_number, write_protected
from webui.forms.settings import TypeEdit
from webui.service.current import (
    current_locks,
    current_reserve_rules,
    load_for,
    snapshot_mtime,
)
from webui.service.results import PieceView, piece_view
from webui.service.scores import keep_potentials, known_potentials
from webui.service.views import (
    ChampionRow,
    Choice,
    champion_row,
    set_name,
    slot_label,
)


@dataclass(frozen=True)
class WeightCell:
    field: str  # the form field, "weight:<stat>"
    label: str
    value: float


@dataclass(frozen=True)
class MainOption:
    field: str  # the form field, "main:<slot>:<stat>"
    label: str
    on: bool


@dataclass(frozen=True)
class MainsCell:
    slot: str
    options: list[MainOption]


@dataclass(frozen=True)
class TypeRow:
    """A champion type, editable as a whole (`forms.settings.parse_champion_type`)."""

    key: str
    label: str
    kind: str
    faction: str  # the game's name, "" for any
    champions: list[str]  # who a seeded faction type was made from
    cells: list[WeightCell]  # per `WeightTable.stats` column
    mains: list[MainsCell]


@dataclass(frozen=True)
class SetColumn:
    set_id: int
    set_name: str
    factor: float


@dataclass(frozen=True)
class TargetRow:
    """A type across the sets: whether each (in `SetGrid.columns` order) targets it."""

    key: str
    label: str
    faction: str | None  # display name
    on: list[bool]


@dataclass(frozen=True)
class TargetGroup:
    kind: str
    rows: list[TargetRow]


@dataclass(frozen=True)
class SetGrid:
    """The sets (most valued first) across, the types down, grouped by kind."""

    columns: list[SetColumn]
    groups: list[TargetGroup]
    off_target: float


@dataclass(frozen=True)
class WeightTable:
    """The champion types and the set fits, editable."""

    stats: list[str]  # the columns' labels
    rows: list[TypeRow]
    kinds: list[Choice]
    factions: list[Choice]  # those a type may be for, by display name
    sets: SetGrid


@dataclass(frozen=True)
class AccessoryRow:
    """An accessory (the optimiser's `PieceView`) and its scores. Scores are quantile scores in
    average rolls; `rework` is None where a rework isn't open to it."""

    piece: PieceView
    where: str  # "inventory", "mailbox", "worn"
    reworked: bool
    fit: str | None  # the champion type it's best for
    now: str
    natural: str  # at +16
    rework: str | None
    scarcity: str  # "×1.15"
    value: str
    protected: bool


@dataclass(frozen=True)
class DropRow:
    row: AccessoryRow
    group: str  # its place in its group: "3rd of 5, keeps 2"
    surplus: bool


@dataclass(frozen=True)
class CandidateRow:
    row: AccessoryRow
    before: str
    after: str
    priority: str


@dataclass(frozen=True)
class SwapRow:
    """The two pieces, through the champion's eyes (the worn one is theirs)."""

    better: AccessoryRow  # to equip
    worn: AccessoryRow  # coming off
    gain: str
    then_sell: bool


@dataclass(frozen=True)
class SwapGroup:
    """A champion wearing pieces a loose one clearly beats, and the swaps: equipped together
    (`artifact_ids`)."""

    champion: ChampionRow
    swaps: list[SwapRow]
    gain: str
    artifact_ids: list[int]


@dataclass(frozen=True)
class SetSummary:
    set_name: str
    role: str
    loose: int  # inventory and mailbox
    to_sell: int
    leave_unclaimed: int


@dataclass(frozen=True)
class CleanupView:
    space: int
    target_free: int
    inventory: int
    mailbox: int
    worn: int
    kept: int
    keep_reasons: dict[str, int]  # how many each rule keeps (a piece may have several)
    to_sell: list[DropRow]
    to_claim: int
    leave_unclaimed: list[DropRow]
    free_after: int
    short: int
    sets: list[SetSummary]
    swaps: int
    sold_after_swaps: int


@dataclass(frozen=True)
class EnhanceView:
    roll: list[CandidateRow]
    finish: list[CandidateRow]
    rework: list[CandidateRow]
    shown: int  # the most each list shows


@dataclass(frozen=True)
class AccessoriesPage:
    tab: str  # one of `ACCESSORY_TABS`
    swaps: list[SwapGroup]
    cleanup: CleanupView
    enhance: EnhanceView
    weights: WeightTable


@dataclass(frozen=True)
class RowContext:
    """What every accessory row reads beyond the piece: read once per page."""

    account: Account
    protected: set[int]
    type_labels: dict[str, str]


ACCESSORY_TABS = ("swaps", "roll", "rework", "cleanup", "weights")  # the workflow's order
ENHANCE_SHOWN = 150
TARGET_FREE = "target_free"  # the store's name for it
TARGET_LABELS = {  # what a set targets, by its types' kinds
    frozenset({Kind.DAMAGE, Kind.SUPPORT}): "Hybrid",
    frozenset({Kind.DAMAGE}): "Damage",
    frozenset({Kind.SUPPORT}): "Support",
}


def accessories_page(account: Account, tab: str) -> AccessoriesPage:
    assessment = current_assessment(account)
    plan = current_plan(account, assessment)
    return AccessoriesPage(
        tab=tab,
        swaps=swap_groups(account, plan),
        cleanup=cleanup_view(account, plan),
        enhance=enhance_view(account, assessment, plan),
        weights=weight_table(account),
    )


def set_target_free(target: int) -> None:
    write_number(STORE, TARGET_FREE, target)


def protect_accessory(artifact_id: int, protected: bool) -> None:
    write_protected(STORE, artifact_id, protected)


def save_type(account: Account, edit: TypeEdit) -> bool:
    """False if the type is gone (deleted on another page)."""
    if (known := find_type(account, edit.key)) is None:
        return False

    save_champion_type(
        STORE,
        replace(
            known,
            label=edit.label,
            kind=edit.kind,
            faction=edit.faction,
            weights=edit.weights,
            mains=edit.mains,
        ),
    )
    return True


def add_type() -> None:
    """A blank one, for any faction: the user fills it in."""
    blank = ChampionType("", "New type", Kind.DAMAGE, (), ())
    add_champion_type(STORE, blank)


def copy_type(account: Account, key: str) -> None:
    """The copy targets the sets its original does."""
    if (known := find_type(account, key)) is None:
        return

    sets = current_sets(account)
    copy = str(
        add_champion_type(STORE, replace(known, label=f"{known.label} (copy)", champions=()))
    )

    for set_id, fit in sets.fits:
        if key in fit.off:
            save_set_fit(STORE, set_id, replace(fit, off=fit.off | {copy}))


def save_set_value(account: Account, set_id: int, factor: float) -> None:
    fit = current_sets(account).fit(set_id)
    save_set_fit(STORE, set_id, replace(fit, factor=factor))


def save_set_target(account: Account, set_id: int, type_key: str, on: bool) -> None:
    fit = current_sets(account).fit(set_id)
    off = fit.off - {type_key} if on else fit.off | {type_key}
    save_set_fit(STORE, set_id, replace(fit, off=off))


def save_off_target(share: float) -> None:
    set_off_target(STORE, share)


def delete_type(key: str) -> None:
    if key.isdigit():
        delete_champion_type(STORE, key)


def find_type(account: Account, key: str) -> ChampionType | None:
    return next((t for t in current_types(account) if t.key == key), None)


def type_factions(account: Account) -> set[str]:
    """The factions a type may be for: the account's champions'."""
    return {champion.faction for champion in account.champions.values()}


def pieces_to_sell(account: Account) -> set[int]:
    """What the plan sells now, so a stale page can't sell what it no longer would."""
    plan = current_plan(account, current_assessment(account))
    return {placed.piece.artifact.id for placed in plan.to_sell}


def current_assessment(account: Account) -> Assessment:
    """Of the current snapshot: `account` is `current_account()`. Locks change often and
    cheaply, so only the potentials are cached."""
    types = current_types(account)
    scorer, potentials = potentials_for(snapshot_mtime(), types, current_sets(account))
    return assess_accessories(account, potentials, current_locks(), scorer)


def current_types(account: Account) -> tuple[ChampionType, ...]:
    """Seeded from `account`'s roster the first time."""
    return read_champion_types(STORE, account)


def current_sets(account: Account) -> SetTable:
    """Seeded from the set roles and tiers, against the types, the first time."""
    return read_set_table(STORE, current_types(account))


@lru_cache(maxsize=4)
def potentials_for(
    snapshot_mtime: int, types: tuple[ChampionType, ...], sets: SetTable
) -> tuple[Scorer, dict[Piece, Potential]]:
    """Cached; scores are also kept on disk (`scores`), so only pieces new to the scorer are
    scored. The snapshot's mtime is only the cache key."""
    account = load_for(snapshot_mtime)
    scorer = make_scorer(types, sets, account.tables.gear, account.tables.glyphs)
    known = known_potentials(POTENTIALS, scorer)
    potentials = potentials_of(account, scorer, known)

    if potentials.keys() != known.keys():
        keep_potentials(POTENTIALS, scorer, potentials)

    return scorer, potentials


def current_plan(account: Account, assessment: Assessment) -> Plan:
    """Reserved pieces are kept like protected ones (swaps may still move them)."""
    reserved = set(reservations(account, current_reserve_rules()))
    return plan_cleanup(assessment, read_protected(STORE), reserved, current_target_free())


def current_target_free() -> int:
    stored = read_number(STORE, TARGET_FREE)
    return DEFAULT_TARGET_FREE if stored is None else int(stored)


def cleanup_view(account: Account, plan: Plan) -> CleanupView:
    context = row_context(account)
    reasons = Counter(reason.value for placed in plan.kept for reason in placed.keep)

    return CleanupView(
        space=plan.space,
        target_free=plan.target_free,
        inventory=plan.inventory,
        mailbox=plan.mailbox,
        worn=plan.worn,
        kept=len(plan.kept),
        keep_reasons=dict(reasons.most_common()),
        to_sell=[drop_row(context, placed) for placed in plan.to_sell],
        to_claim=len(plan.to_claim),
        leave_unclaimed=[drop_row(context, placed) for placed in plan.leave_unclaimed],
        free_after=plan.free_after(),
        short=plan.short,
        sets=set_summaries(account, plan),
        swaps=len(plan.swaps),
        sold_after_swaps=plan.sold_after_swaps(),
    )


def enhance_view(account: Account, assessment: Assessment, plan: Plan) -> EnhanceView:
    dropped, context = plan.dropped(), row_context(account)

    def rows(candidates: list[Candidate]) -> list[CandidateRow]:
        return [
            CandidateRow(
                accessory_row(context, c.piece),
                f"{c.before:.1f}",
                f"{c.after:.1f}",
                f"{c.priority:.1f}",
            )
            for c in candidates[:ENHANCE_SHOWN]
        ]

    return EnhanceView(
        roll=rows(roll_list(assessment, dropped)),
        finish=rows(finish_list(assessment, dropped)),
        rework=rows(rework_list(assessment, dropped)),
        shown=ENHANCE_SHOWN,
    )


def weight_table(account: Account) -> WeightTable:
    types, sets = current_types(account), current_sets(account)

    def type_row(champion_type: ChampionType) -> TypeRow:
        suits = dict(champion_type.mains)
        return TypeRow(
            key=champion_type.key,
            label=champion_type.label,
            kind=champion_type.kind.value,
            faction=champion_type.faction or "",
            champions=list(champion_type.champions),
            cells=[
                WeightCell(f"weight:{stat.value}", STAT_LABELS[stat], champion_type.weight(stat))
                for stat in TYPE_STATS
            ],
            mains=[
                MainsCell(
                    slot_label(slot),
                    [
                        MainOption(
                            f"main:{slot.value}:{stat.value}",
                            STAT_LABELS[stat],
                            stat in suits.get(slot, ()),
                        )
                        for stat in stats
                    ],
                )
                for slot, stats in ACCESSORY_MAINS
            ],
        )

    return WeightTable(
        stats=[STAT_LABELS[stat] for stat in TYPE_STATS],
        rows=[
            type_row(champion_type)
            # any faction's first, then by faction; oldest first within
            for champion_type in sorted(types, key=lambda t: t.faction or "")
        ],
        kinds=[Choice(kind.value, kind.value.capitalize()) for kind in Kind],
        factions=sorted(
            (Choice(faction, faction_label(faction)) for faction in type_factions(account)),
            key=lambda choice: choice.label,
        ),
        sets=set_grid(account, types, sets),
    )


def set_grid(account: Account, types: tuple[ChampionType, ...], sets: SetTable) -> SetGrid:
    """Types in the type table's order: any faction's first."""
    columns = sorted(
        (
            SetColumn(set_id, set_name(account, set_id), sets.factor(set_id))
            for set_id in listed_sets(account, sets)
        ),
        key=lambda column: (-column.factor, column.set_name),
    )
    ordered = sorted(types, key=lambda t: t.faction or "")

    def row(champion_type: ChampionType) -> TargetRow:
        return TargetRow(
            champion_type.key,
            champion_type.label,
            faction_label(champion_type.faction) if champion_type.faction else None,
            [sets.targets(column.set_id, champion_type) for column in columns],
        )

    groups = [
        TargetGroup(kind.value.capitalize(), [row(t) for t in ordered if t.kind is kind])
        for kind in Kind
    ]
    return SetGrid(columns, groups, sets.off_target)


def listed_sets(account: Account, sets: SetTable) -> set[int]:
    """The table's sets and any the account's accessories are of."""
    pieces = (*account.artifacts, *account.mailbox)
    return {set_id for set_id, _ in sets.fits} | {a.set_id for a in pieces if a.slot in ACCESSORIES}


def targets_label(kinds: set[Kind]) -> str:
    return TARGET_LABELS.get(frozenset(kinds), "None")


def set_summaries(account: Account, plan: Plan) -> list[SetSummary]:
    """Most dropped first."""
    types, sets = current_types(account), current_sets(account)
    loose: Counter[int] = Counter(
        p.group.set_id for p in (*plan.kept, *plan.to_sell, *plan.leave_unclaimed)
    )
    sold = Counter(p.group.set_id for p in plan.to_sell)
    unclaimed = Counter(p.group.set_id for p in plan.leave_unclaimed)

    summaries = [
        SetSummary(
            set_name(account, set_id),
            targets_label(sets.kinds(set_id, types)),
            count,
            sold[set_id],
            unclaimed[set_id],
        )
        for set_id, count in loose.items()
    ]
    return sorted(summaries, key=lambda s: (-(s.to_sell + s.leave_unclaimed), s.set_name))


def swap_groups(account: Account, plan: Plan) -> list[SwapGroup]:
    """By champion, the biggest total gain first."""
    context = row_context(account)
    reserved = reservations(account, current_reserve_rules())
    by_champion: dict[int, list[Swap]] = {}

    for swap in plan.swaps:
        by_champion.setdefault(swap.champion_id, []).append(swap)

    def gain(swaps: list[Swap]) -> float:
        return sum(swap.pairing.gain() for swap in swaps)

    return [
        SwapGroup(
            champion=champion_row(account.champions[champion_id]),
            swaps=[
                swap_row(context, swap, account.champions[champion_id], reserved) for swap in swaps
            ],
            gain=f"+{gain(swaps):.1f}",
            artifact_ids=[swap.pairing.better.artifact.id for swap in swaps],
        )
        for champion_id, swaps in sorted(by_champion.items(), key=lambda item: -gain(item[1]))
        if champion_id in account.champions
    ]


def swap_row(
    context: RowContext, swap: Swap, champion: Champion, reserved: Reservations
) -> SwapRow:
    return SwapRow(
        better=accessory_row(context, swap.pairing.better, champion, reserved),
        worn=accessory_row(context, swap.pairing.worn, champion, reserved),
        gain=f"+{swap.pairing.gain():.1f}",
        then_sell=swap.then_sell,
    )


def drop_row(context: RowContext, placed: Placed) -> DropRow:
    group = f"{ordinal(placed.place)} of its group, keeps {placed.quota}"
    return DropRow(accessory_row(context, placed.piece), group, placed.surplus())


def row_context(account: Account) -> RowContext:
    return RowContext(account, read_protected(STORE), type_labels(account))


def accessory_row(
    context: RowContext,
    piece: Assessed,
    champion: Champion | None = None,
    reserved: Reservations | None = None,
) -> AccessoryRow:
    """The piece through `champion`'s eyes (a swap's), or nobody's (the lists')."""
    artifact, potential = piece.artifact, piece.potential

    return AccessoryRow(
        piece=piece_view(artifact, context.account, champion, reserved),
        where=piece.where.value,
        reworked=artifact.reworked,
        fit=context.type_labels.get(potential.natural.fit or "", None),
        now=f"{potential.now.best:.1f}",
        natural=f"{potential.natural.best:.1f}",
        rework=f"{potential.rework.best:.1f}" if potential.rework else None,
        scarcity=f"×{piece.scarcity:g}",
        value=f"{piece.value:.1f}",
        protected=artifact.id in context.protected,
    )


def type_labels(account: Account) -> dict[str, str]:
    """Type key -> its label; a faction's own types name the faction."""
    return {
        t.key: f"{t.label} ({faction_label(t.faction)})" if t.faction else t.label
        for t in current_types(account)
    }


def ordinal(place: int) -> str:
    suffix = "th" if 10 <= place % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(place % 10, "th")
    return f"{place}{suffix}"
