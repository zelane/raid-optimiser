"""
accessories.py - the accessories pages: swaps, the roll and rework lists, the clean-up, and
the champion type weights. Assessing every accessory takes a couple of seconds, so the
assessment is cached per capture, type weights and locks.

- `WeightCell`, `WeightRow`, `FactionTypeRow`, `SetTierRow`, `WeightTable`, `AccessoryRow`,
  `DropRow`, `CandidateRow`, `SwapRow`, `SwapGroup`, `SetSummary`, `CleanupView`,
  `EnhanceView`, `AccessoriesPage`, `RowContext`: the views
- `ACCESSORY_TABS`, `ENHANCE_SHOWN`, `TARGET_FREE`: their shape
- `accessories_page`, `cleanup_page`, `set_target_free`, `protect_accessory`,
  `change_type_weight`, `pieces_to_sell`: what the pages ask for
- `current_assessment` (`assessment_for`, cached), `current_plan`, `current_target_free`: the
  state they're made from
- `cleanup_view`, `enhance_view`, `weight_table` (`tier_reason`), `set_summaries`,
  `swap_groups`, `swap_row`, `drop_row`, `row_context`, `accessory_row`, `type_labels`,
  `ordinal`: what they share
"""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from optimiser.accessories.assess import Assessed, Assessment, assess_accessories
from optimiser.accessories.cleanup import DEFAULT_TARGET_FREE, Placed, Plan, Swap, plan_cleanup
from optimiser.accessories.enhance import Candidate, finish_list, rework_list, roll_list
from optimiser.accessories.potential import make_scorer
from optimiser.accessories.roles import (
    NO_SET,
    SET_ROLES,
    SET_TIERS,
    TYPE_STATS,
    ChampionType,
    TypeKey,
    set_factor,
    set_role,
)
from optimiser.account import Account, Stat
from optimiser.labels import STAT_LABELS, format_line, line_label
from optimiser.paths import STORE
from optimiser.settings import read_standard_types, set_type_weight
from optimiser.store import read_number, read_protected, write_number, write_protected
from webui.service.current import capture_mtime, current_locks, load_for, roster_types
from webui.service.views import (
    ChampionRow,
    asset_url,
    champion_row,
    piece_image_url,
    set_name,
    slot_label,
)


@dataclass(frozen=True)
class WeightCell:
    field: str  # the form field: "<type>:<stat>", by the store's names
    value: float


@dataclass(frozen=True)
class WeightRow:
    champion_type: str
    cells: list[WeightCell]


@dataclass(frozen=True)
class FactionTypeRow:
    faction: str
    label: str
    champions: list[str]
    weights: list[str]  # per `WeightTable.stats` column, "" for 0
    mains: str  # "Ring ATK/HP · Amulet C.DMG · Banner ATK/HP/ACC"


@dataclass(frozen=True)
class SetTierRow:
    set_name: str
    role: str
    factor: str  # "×1.3"
    reason: str


@dataclass(frozen=True)
class WeightTable:
    """The standard types, editable, the faction types made from the roster, and the sets'
    roles and meta tiers."""

    stats: list[str]  # the columns' labels
    rows: list[WeightRow]
    faction_rows: list[FactionTypeRow]
    sets: list[SetTierRow]


@dataclass(frozen=True)
class AccessoryRow:
    """An accessory as the lists show it. Scores are quantile scores in average rolls;
    `rework` is None where a rework isn't open to it."""

    id: int
    slot: str
    set_name: str
    image_url: str | None
    faction: str | None
    faction_icon_url: str | None
    rank: int
    rarity: str
    level: int
    main: str
    substats: list[str]
    where: str  # "inventory", "mailbox", "worn"
    worn_by: str | None
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
    better: AccessoryRow  # to equip
    worn: AccessoryRow  # coming off
    gain: str
    then_sell: bool


@dataclass(frozen=True)
class SwapGroup:
    """A champion wearing pieces a loose one clearly beats, and the swaps: equipped together
    (`artifact_ids`, comma-separated, as the equip button posts them)."""

    champion: ChampionRow
    swaps: list[SwapRow]
    gain: str
    artifact_ids: str


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


def accessories_page(account: Account, tab: str) -> AccessoriesPage:
    assessment = current_assessment(account)
    plan = current_plan(assessment)
    return AccessoriesPage(
        tab=tab,
        swaps=swap_groups(account, plan),
        cleanup=cleanup_view(account, plan),
        enhance=enhance_view(account, assessment, plan),
        weights=weight_table(account),
    )


def cleanup_page(account: Account) -> CleanupView:
    return cleanup_view(account, current_plan(current_assessment(account)))


def set_target_free(account: Account, target: int) -> CleanupView:
    write_number(STORE, TARGET_FREE, target)
    return cleanup_page(account)


def protect_accessory(account: Account, artifact_id: int, protected: bool) -> CleanupView:
    write_protected(STORE, artifact_id, protected)
    return cleanup_page(account)


def change_type_weight(key: TypeKey, stat: Stat, weight: float) -> None:
    set_type_weight(STORE, key, stat, weight)


def pieces_to_sell(account: Account) -> set[int]:
    """What the plan sells now, so a stale page can't sell what it no longer would."""
    plan = current_plan(current_assessment(account))
    return {placed.piece.artifact.id for placed in plan.to_sell}


def current_assessment(account: Account) -> Assessment:
    """Of the current capture: `account` is `current_account()`."""
    types = read_standard_types(STORE)
    locks = tuple(sorted(current_locks().items()))
    return assessment_for(capture_mtime(), types, locks)


@lru_cache(maxsize=4)
def assessment_for(
    capture_mtime: int, types: tuple[ChampionType, ...], locks: tuple[tuple[int, int], ...]
) -> Assessment:
    """Cached (assessing every accessory takes a couple of seconds); the capture's mtime is
    only the cache key."""
    account = load_for(capture_mtime)
    every_type = (*types, *roster_types(capture_mtime))
    return assess_accessories(account, make_scorer(every_type, account.tables.gear), dict(locks))


def current_plan(assessment: Assessment) -> Plan:
    return plan_cleanup(assessment, read_protected(STORE), current_target_free())


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
    standard = {TypeKey(t.key): t for t in read_standard_types(STORE)}

    def faction_row(own: ChampionType) -> FactionTypeRow:
        return FactionTypeRow(
            faction=own.faction or "",
            label=own.label,
            champions=list(own.champions),
            weights=[f"{own.weight(stat):g}" if own.weight(stat) else "" for stat in TYPE_STATS],
            mains=" · ".join(
                f"{slot_label(slot)} {'/'.join(STAT_LABELS[m] for m in mains)}"
                for slot, mains in own.mains
            ),
        )

    return WeightTable(
        stats=[STAT_LABELS[stat] for stat in TYPE_STATS],
        rows=[
            WeightRow(
                standard[key].label,
                [
                    WeightCell(f"{key.value}:{stat.value}", standard[key].weight(stat))
                    for stat in TYPE_STATS
                ],
            )
            for key in TypeKey
        ],
        sets=[
            SetTierRow(
                set_name(account, set_id),
                role.value,
                f"×{set_factor(set_id):g}",
                tier_reason(set_id),
            )
            for set_id, role in sorted(SET_ROLES.items(), key=lambda item: -set_factor(item[0]))
        ],
        faction_rows=[
            faction_row(own)
            for own in sorted(
                roster_types(capture_mtime()), key=lambda t: (t.faction or "", t.label)
            )
        ],
    )


def tier_reason(set_id: int) -> str:
    if tier := SET_TIERS.get(set_id):
        return tier.reason

    return "set-less: kept only when very good" if set_id == NO_SET else ""


def set_summaries(account: Account, plan: Plan) -> list[SetSummary]:
    """Most dropped first."""
    loose: Counter[int] = Counter(
        p.group.set_id for p in (*plan.kept, *plan.to_sell, *plan.leave_unclaimed)
    )
    sold = Counter(p.group.set_id for p in plan.to_sell)
    unclaimed = Counter(p.group.set_id for p in plan.leave_unclaimed)

    summaries = [
        SetSummary(
            set_name(account, set_id),
            set_role(set_id).value,
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
    by_champion: dict[int, list[Swap]] = {}

    for swap in plan.swaps:
        by_champion.setdefault(swap.champion_id, []).append(swap)

    def gain(swaps: list[Swap]) -> float:
        return sum(swap.pairing.gain() for swap in swaps)

    return [
        SwapGroup(
            champion=champion_row(account.champions[champion_id]),
            swaps=[swap_row(context, swap) for swap in swaps],
            gain=f"+{gain(swaps):.1f}",
            artifact_ids=",".join(str(swap.pairing.better.artifact.id) for swap in swaps),
        )
        for champion_id, swaps in sorted(by_champion.items(), key=lambda item: -gain(item[1]))
        if champion_id in account.champions
    ]


def swap_row(context: RowContext, swap: Swap) -> SwapRow:
    return SwapRow(
        better=accessory_row(context, swap.pairing.better),
        worn=accessory_row(context, swap.pairing.worn),
        gain=f"+{swap.pairing.gain():.1f}",
        then_sell=swap.then_sell,
    )


def drop_row(context: RowContext, placed: Placed) -> DropRow:
    group = f"{ordinal(placed.place)} of its group, keeps {placed.quota}"
    return DropRow(accessory_row(context, placed.piece), group, placed.surplus())


def row_context(account: Account) -> RowContext:
    return RowContext(account, read_protected(STORE), type_labels())


def accessory_row(context: RowContext, piece: Assessed) -> AccessoryRow:
    account = context.account
    artifact, potential = piece.artifact, piece.potential
    wearer = account.champions.get(account.owners.get(artifact.id, -1))

    return AccessoryRow(
        id=artifact.id,
        slot=slot_label(artifact.slot),
        set_name=set_name(account, artifact.set_id),
        image_url=piece_image_url(artifact),
        faction=artifact.faction,
        faction_icon_url=asset_url("factions", artifact.faction) if artifact.faction else None,
        rank=artifact.rank,
        rarity=artifact.rarity,
        level=artifact.level,
        main=line_label(artifact.primary),
        substats=[format_line(line) for line in artifact.substats],
        where=piece.where.value,
        worn_by=wearer.name if wearer else None,
        reworked=artifact.reworked,
        fit=context.type_labels.get(potential.natural.fit or "", None),
        now=f"{potential.now.best:.1f}",
        natural=f"{potential.natural.best:.1f}",
        rework=f"{potential.rework.best:.1f}" if potential.rework else None,
        scarcity=f"×{piece.scarcity:g}",
        value=f"{piece.value:.1f}",
        protected=artifact.id in context.protected,
    )


def type_labels() -> dict[str, str]:
    """Type key -> its label; a faction's own types name the faction."""
    labels = {t.key: t.label for t in read_standard_types(STORE)}
    labels |= {t.key: f"{t.label} ({t.faction})" for t in roster_types(capture_mtime())}
    return labels


def ordinal(place: int) -> str:
    suffix = "th" if 10 <= place % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(place % 10, "th")
    return f"{place}{suffix}"
