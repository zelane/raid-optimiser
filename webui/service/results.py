"""
results.py - a solve as the champion page shows it: the builds against the champion's
current gear, or why there are none.

- `StatCell`, `LineView`, `PieceView`, `BuildView`, `ResultsView`, `ShortfallView`,
  `Outcome`: the views (saved with runs, so fields added later have defaults)
- `solve`: the workflow (`Stopped` if stopped before a build was found)
- `results_view`, `shortfall_view`: its outcomes
- `build_view`, `piece_view`, `line_view`, `stat_cells`, `damage_cell`: what they share
"""

import time
from dataclasses import dataclass, field

from optimiser.account import (
    Account,
    Artifact,
    Champion,
    Slot,
    Stat,
    StatLine,
    Stats,
    faction_label,
    worn_gear,
)
from optimiser.assume import assume
from optimiser.damage import estimate_damage
from optimiser.labels import STAT_LABELS, format_stat, line_amount, line_label, reason_label
from optimiser.paths import STORE
from optimiser.reserve import Reservations, Worn
from optimiser.settings import read_assumptions
from optimiser.solve import Build, Request, SetsRuleOut, Shortfall, Stopped, find_builds
from optimiser.stats import build_stats, set_multiplier
from webui.service.views import (
    ChampionRow,
    StarView,
    asset_url,
    champion_row,
    piece_image_url,
    set_name,
    slot_label,
    star_views,
)


@dataclass(frozen=True)
class StatCell:
    """A stat total, and how it compares with the champion's current gear."""

    label: str
    text: str
    change: str | None  # "+1200", "-3%"; None when unchanged or for current gear
    better: bool | None


@dataclass(frozen=True)
class LineView:
    """`planned_glyph` is an assumed glyph, better than the one on it now (`glyph`)."""

    label: str
    amount: str
    glyph: str | None
    rolls: int
    optimised: bool  # False for stats the optimiser ignores (damage dealt/taken)
    # The defaults are for runs saved before these existed.
    planned_glyph: str | None = None
    planned_amount: str | None = None  # once levelled or ascended further


@dataclass(frozen=True)
class PieceView:
    """Everything needed to find the piece in game."""

    id: int
    slot: str
    set_name: str
    set_icon_url: str | None
    image_url: str | None  # the piece's art, as the game shows it
    rank: int
    rarity: str
    level: int
    primary: LineView
    substats: list[LineView]
    ascension: LineView | None
    faction: str | None
    worn_by: str | None  # another champion, if it has to be taken off them
    worn_by_portrait: str | None  # whoever wears it, this champion included
    equipped: bool  # the champion already wears it
    # The defaults are for runs saved before these existed.
    stars: list[StarView] = field(default_factory=list)
    ascend_level: int = 0
    planned_level: int | None = None  # assumed levelled to this
    planned_ascend_level: int | None = None  # assumed ascended to this
    reserved_by: list[str] = field(default_factory=list)  # reserve rules keeping it elsewhere
    faction_icon_url: str | None = None  # an accessory's faction lock, as its banner
    faction_label: str | None = None  # the lock as the game names it ("Dark Elves")


@dataclass(frozen=True)
class BuildView:
    """`slots` holds every slot in the game's order (weapon first), None where the build
    leaves an accessory slot empty."""

    number: int
    stats: list[StatCell]
    slots: list[PieceView | None]
    artifact_ids: list[int]
    from_others: int
    equipped: int
    # The defaults are for runs saved before these existed.
    glyphs_to_apply: int = 0
    to_level: int = 0
    to_ascend: int = 0


@dataclass(frozen=True)
class ResultsView:
    champion: ChampionRow
    lore_of_steel: bool
    damage: str | None  # what the DMG column measures, when damage is ranked
    current: list[StatCell]
    builds: list[BuildView]
    seconds: float
    champion_level_note: str | None = None  # "at L60 (now L52)"; the default is for old runs


@dataclass(frozen=True)
class ShortfallView:
    reason: str | None
    lines: list[str]


type Outcome = ResultsView | ShortfallView


def solve(account: Account, request: Request, reserved: Reservations) -> Outcome | Stopped:
    """`reserved`: what every reserve rule keeps, to note on pieces (whichever the request
    keeps out)."""
    assumed, request = assume(account, request, read_assumptions(STORE, account))
    started = time.monotonic()
    outcome = find_builds(assumed, request)
    seconds = time.monotonic() - started

    match outcome:
        case Stopped():
            return outcome

        case SetsRuleOut(reason=reason):
            return ShortfallView(reason, [])

        case Shortfall() as shortfall:
            return shortfall_view(shortfall, request)

        case builds:
            return results_view(account, request, builds, seconds, reserved)


def results_view(
    account: Account,
    request: Request,
    builds: list[Build],
    seconds: float,
    reserved: Reservations,
) -> ResultsView:
    """The builds against the champion's current gear (as they are, nothing assumed)."""
    champion = request.champion
    sets = account.tables.sets
    worn = worn_gear(account, champion)
    current = build_stats(champion, worn, account.tables)
    goal = request.damage_goal()
    current_damage = estimate_damage(goal, current, worn, sets) if goal else None

    def damage_cells(stats: Stats, artifacts: tuple[Artifact, ...]) -> list[StatCell]:
        if goal is None:
            return []

        return [damage_cell(estimate_damage(goal, stats, artifacts, sets), current_damage)]

    return ResultsView(
        champion=champion_row(champion),
        lore_of_steel=set_multiplier(champion, account.tables) > 1,
        damage=f"{goal.skill_name} crit vs {goal.enemy_defence:g} DEF" if goal else None,
        current=stat_cells(current, None) + damage_cells(current, tuple(worn)),
        builds=[
            build_view(
                n,
                build,
                current,
                account,
                champion,
                damage_cells(build.stats, build.artifacts),
                reserved,
            )
            for n, build in enumerate(builds, 1)
        ],
        seconds=seconds,
        champion_level_note=(
            f"at L{champion.level} (now L{account.champions[champion.id].level})"
            if champion.level != account.champions[champion.id].level
            else None
        ),
    )


def shortfall_view(shortfall: Shortfall, request: Request) -> ShortfallView:
    highest = [
        f"{STAT_LABELS[stat]} at least {format_stat(stat, request.minimums[stat])}: "
        f"best possible {format_stat(stat, best)}"
        for stat, best in shortfall.highest.items()
    ]
    lowest = [
        f"{STAT_LABELS[stat]} at most {format_stat(stat, request.maximums[stat])}: "
        f"lowest possible {format_stat(stat, low)}"
        for stat, low in shortfall.lowest.items()
    ]
    return ShortfallView(None, highest + lowest)


def build_view(
    number: int,
    build: Build,
    current: Stats,
    account: Account,
    champion: Champion,
    extra_cells: list[StatCell],
    reserved: Reservations,
) -> BuildView:
    by_slot = {a.slot: piece_view(a, account, champion, reserved) for a in build.artifacts}
    pieces = list(by_slot.values())
    return BuildView(
        number=number,
        stats=stat_cells(build.stats, current) + extra_cells,
        slots=[by_slot.get(slot) for slot in Slot],
        artifact_ids=[artifact.id for artifact in build.artifacts],
        from_others=sum(1 for p in pieces if p.worn_by),
        equipped=sum(1 for p in pieces if p.equipped),
        glyphs_to_apply=sum(1 for p in pieces for line in p.substats if line.planned_glyph),
        to_level=sum(1 for p in pieces if p.planned_level),
        to_ascend=sum(1 for p in pieces if p.planned_ascend_level),
    )


def piece_view(
    artifact: Artifact,
    account: Account,
    champion: Champion | None = None,
    reserved: Reservations | None = None,
) -> PieceView:
    """Through `champion`'s eyes (a piece they wear is `equipped`; reasons through the
    champion themselves, their own tag or team, aren't noted), or nobody's: who wears it."""
    owner_id = account.owners.get(artifact.id)
    wearer = account.champions.get(owner_id) if owner_id is not None else None
    mine = champion is not None and owner_id == champion.id
    owner = None if mine else wearer

    return PieceView(
        id=artifact.id,
        slot=slot_label(artifact.slot),
        set_name=set_name(account, artifact.set_id),
        set_icon_url=asset_url("sets", str(artifact.set_id)),
        image_url=piece_image_url(artifact),
        rank=artifact.rank,
        rarity=artifact.rarity,
        level=artifact.level,
        primary=line_view(artifact.primary),
        substats=[line_view(line) for line in artifact.substats],
        ascension=line_view(artifact.ascension) if artifact.ascension else None,
        stars=star_views(artifact.rank, artifact.ascend_level, 0),
        ascend_level=artifact.ascend_level,
        planned_level=artifact.planned_level,
        planned_ascend_level=artifact.planned_ascend_level,
        faction=artifact.faction,
        faction_icon_url=asset_url("factions", artifact.faction) if artifact.faction else None,
        faction_label=faction_label(artifact.faction) if artifact.faction else None,
        worn_by=owner.name if owner else None,
        worn_by_portrait=champion_row(wearer).portrait_url if wearer else None,
        equipped=mine,
        reserved_by=[
            reason_label(reason, account)
            for reason in (reserved or {}).get(artifact.id, ())
            if not (isinstance(reason, Worn) and champion and reason.champion_id == champion.id)
        ],
    )


def line_view(line: StatLine) -> LineView:
    return LineView(
        label=line_label(line),
        amount=line_amount(line.value, line.absolute),
        glyph=f"+{line_amount(line.glyph, line.absolute)}" if line.glyph else None,
        rolls=line.rolls,
        optimised=line.stat is not None,
        planned_glyph=(
            f"+{line_amount(line.planned_glyph, line.absolute)}" if line.planned_glyph else None
        ),
        planned_amount=(
            line_amount(line.planned_value, line.absolute)
            if line.planned_value is not None
            else None
        ),
    )


def stat_cells(stats: Stats, current: Stats | None) -> list[StatCell]:
    """Each stat's total; against `current`, also how much it changes."""
    cells = []

    for stat in Stat:
        text = format_stat(stat, stats[stat])
        if current is None or text == format_stat(stat, current[stat]):
            cells.append(StatCell(STAT_LABELS[stat], text, None, None))
            continue

        delta = stats[stat] - current[stat]
        change = format_stat(stat, abs(delta))
        cells.append(
            StatCell(STAT_LABELS[stat], text, ("+" if delta > 0 else "-") + change, delta > 0)
        )

    return cells


def damage_cell(damage: float, current: float | None) -> StatCell:
    text = f"{damage:,.0f}"

    if current is None or round(damage) == round(current):
        return StatCell("DMG", text, None, None)

    delta = damage - current
    return StatCell("DMG", text, f"{'+' if delta > 0 else '-'}{abs(delta):,.0f}", delta > 0)
