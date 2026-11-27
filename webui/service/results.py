"""
results.py - a solve as the champion page shows it: the builds against the champion's
current gear, or why there are none.

- `StatCell`, `LineView`, `PieceView`, `BuildView`, `ResultsView`, `ShortfallView`,
  `Outcome`: the views (saved with runs, so fields added later have defaults)
- `solve`: the workflow (`Stopped` if stopped before a build was found)
- `results_view` (`battle_notes`), `shortfall_view`: its outcomes
- `build_view`, `piece_view`, `line_view`, `stat_cells`, `damage_cell`, `rate_cell`,
  `rate_note`, `RATE_LABELS`: what they share
- `check_equip` (`refusal`): a build button's pieces its gear rules no longer allow
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
from optimiser.accuracy import Lands, Resists
from optimiser.assume import assume
from optimiser.battle import Battle
from optimiser.damage import estimate_damage
from optimiser.labels import (
    STAT_LABELS,
    aura_holds,
    aura_label,
    buff_label,
    format_stat,
    line_amount,
    line_label,
    reason_label,
)
from optimiser.paths import STORE
from optimiser.reserve import Reservations, Worn
from optimiser.settings import read_assumptions
from optimiser.solve import (
    Build,
    GearFilter,
    Request,
    SetsRuleOut,
    Shortfall,
    Stopped,
    find_builds,
)
from optimiser.stats import build_stats, set_multiplier
from webui.forms.request import Equip
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
    rates: list[str] = field(default_factory=list)  # what each ranked rate's column measures
    battle: list[str] = field(
        default_factory=list
    )  # the buffs and aura assumed, "Increase SPD 30%"


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
    """The builds against the champion's current gear (as they are, nothing assumed but the
    battle, which every row is in)."""
    champion = request.champion
    sets = account.tables.sets
    worn = worn_gear(account, champion)
    current = build_stats(champion, worn, account.tables, request.battle.bonuses())
    goal = request.damage_goal()
    current_damage = estimate_damage(goal, current, worn, sets) if goal else None

    rates = [goal for goal in request.ranking if isinstance(goal, Lands | Resists)]

    def extra_cells(stats: Stats, artifacts: tuple[Artifact, ...]) -> list[StatCell]:
        rate_cells = [rate_cell(rate, stats, current) for rate in rates]

        if goal is None:
            return rate_cells

        damage = damage_cell(estimate_damage(goal, stats, artifacts, sets), current_damage)
        return [damage, *rate_cells]

    return ResultsView(
        champion=champion_row(champion),
        lore_of_steel=set_multiplier(champion, account.tables) > 1,
        damage=f"{goal.skill_name} crit vs {goal.enemy_defence:g} DEF" if goal else None,
        current=stat_cells(current, None) + extra_cells(current, tuple(worn)),
        rates=[rate_note(rate) for rate in rates],
        battle=battle_notes(request.battle),
        builds=[
            build_view(
                n,
                build,
                current,
                account,
                champion,
                extra_cells(build.stats, build.artifacts),
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


def battle_notes(battle: Battle) -> list[str]:
    """ "Increase SPD 30%", "Roric Wyrmbane's aura (SPD +19%, in Arena)" """
    notes = [buff_label(buff) for buff in battle.buffs]

    if leader := battle.leader:
        holds = aura_holds(leader.aura)
        detail = aura_label(leader.aura) + (f", {holds}" if holds else "")
        notes.append(f"{leader.champion.name}'s aura ({detail})")

    return notes


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


def rate_cell(goal: Lands | Resists, stats: Stats, current: Stats) -> StatCell:
    """A ranked rate's cell: how often debuffs land (`Lands`) or are resisted (`Resists`), and
    the change in percentage points from the gear worn now."""
    label = RATE_LABELS[type(goal)]
    rate, now = goal.rate(stats[goal.stat]), goal.rate(current[goal.stat])
    text = f"{rate:.1%}"

    if text == f"{now:.1%}":
        return StatCell(label, text, None, None)

    return StatCell(label, text, f"{'+' if rate > now else '-'}{abs(rate - now):.1%}", rate > now)


RATE_LABELS = {Lands: "Lands", Resists: "Resists"}


def rate_note(goal: Lands | Resists) -> str:
    match goal:
        case Lands(resistance=resistance):
            return f"Lands is how often its debuffs land against {resistance:g} RES"

        case Resists(accuracy=accuracy):
            return f"Resists is how often it resists debuffs from {accuracy:g} ACC"


def damage_cell(damage: float, current: float | None) -> StatCell:
    text = f"{damage:,.0f}"

    if current is None or round(damage) == round(current):
        return StatCell("DMG", text, None, None)

    delta = damage - current
    return StatCell("DMG", text, f"{'+' if delta > 0 else '-'}{abs(delta):,.0f}", delta > 0)


def check_equip(equip: Equip, account: Account, champion: Champion) -> str | None:
    """The pieces the build's gear rules no longer allow, as the account is now: since it was
    found, a piece went to a champion it may not take from (one locked, or any when it took
    unworn gear only) or a reserve rule took it. "Gloves, Ring: Kro'khad (locked at 5)"."""
    pieces = {artifact.id: artifact for artifact in account.artifacts}
    allowed = equip.team | {champion.id}
    slots_by_reason: dict[str, list[str]] = {}

    for artifact_id in equip.artifact_ids:
        owner = account.owners.get(artifact_id)

        if owner in allowed or equip.gear.allows(artifact_id, owner):
            continue

        reason = refusal(artifact_id, owner, equip.gear, account)
        slots_by_reason.setdefault(reason, []).append(slot_label(pieces[artifact_id].slot))

    if not slots_by_reason:
        return None

    taken = "; ".join(f"{', '.join(slots)}: {reason}" for reason, slots in slots_by_reason.items())
    return f"no longer free to take since the build was found ({taken}): run it again"


def refusal(artifact_id: int, owner: int | None, gear: GearFilter, account: Account) -> str:
    """Why a piece is off limits now: the reserve rules keeping it ("Arena Build I (Arbiter)"),
    else who wears it ("Kro'khad (locked at 5)")."""
    if reasons := gear.reserved.get(artifact_id):
        return ", ".join(reason_label(reason, account) for reason in reasons)

    wearer = account.champions[owner].name if owner in account.champions else "another champion"

    if gear.unworn_only:
        return f"worn by {wearer}"

    return f"worn by {wearer} (locked at {gear.locks.get(owner, 0)})"
