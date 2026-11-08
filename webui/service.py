"""
service.py - what the web pages show, as plain data: no HTML and no web framework, so a JSON
API (for a Vue front end, say) can return the same objects with `dataclasses.asdict`.

- `ChampionRow`, `ListedChampion`, `StatCell`, `LineView`, `PieceView`, `BuildView`: the views
- `SkillOption`, `ResultsView`, `ShortfallView`, `FormOptions`, `ChampionPage`: what a page
  is made of
- `current_account`: the account, reloaded when a new capture lands
- `current_locks`, `lock_champion`: champion locks, kept in the store
- `search_champions`, `champion_page`, `solve`: what the pages ask for
- `load_for`, `champion_row`, `form_options`, `skill_options`, `current_stats`, `current_gear`,
  `shortfall_view`, `build_view`, `piece_view`, `line_view`, `stat_cells`, `damage_cell`,
  `describe_goal`, `asset_url`: what they share
"""

import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from optimiser.account import (
    Account,
    Artifact,
    Champion,
    Slot,
    Stat,
    StatLine,
    Stats,
    load_account,
)
from optimiser.damage import DamageGoal, Unsupported, damage_goal, estimate_damage
from optimiser.labels import (
    PERCENT_STATS,
    STAT_LABELS,
    format_stat,
    line_amount,
    line_label,
    pool_choices,
    pool_label,
    pool_name,
)
from optimiser.solve import Build, Request, Shortfall, find_builds
from optimiser.stats import build_stats, set_multiplier
from optimiser.store import Locks, read_locks, write_lock

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "captures" / "latest"
STATIC = ROOT / "static"
SCHEMA = ROOT / "schema" / "schema.json"
STORE = ROOT / "state" / "optimiser.sqlite"
ASSETS = Path(__file__).resolve().parent / "static" / "assets"
SLOT_ORDER = list(Slot)
SEARCH_LIMIT = 40
SUPPORT_CHECK_DEF = 6000  # any DEF will do: whether a skill can be ranked doesn't depend on it


@dataclass(frozen=True)
class ChampionRow:
    id: int
    name: str
    rarity: str
    grade: int
    level: int
    ascension: int
    awakening: int
    empower: int
    affinity: str
    faction: str
    portrait_url: str | None


@dataclass(frozen=True)
class ListedChampion:
    """A champion on the champion list, with their lock (0: unlocked)."""

    champion: ChampionRow
    lock: int


@dataclass(frozen=True)
class StatCell:
    """A stat total, and how it compares with the champion's current gear."""

    label: str
    text: str
    change: str | None  # "+1200", "-3%"; None when unchanged or for current gear
    better: bool | None


@dataclass(frozen=True)
class LineView:
    label: str
    amount: str
    glyph: str | None
    rolls: int
    optimised: bool  # False for stats the optimiser ignores (damage dealt/taken)


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
    worn_by_portrait: str | None
    equipped: bool  # the champion already wears it


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


@dataclass(frozen=True)
class ResultsView:
    champion: ChampionRow
    lore_of_steel: bool
    damage: str | None  # what the DMG column measures, when damage is ranked
    current: list[StatCell]
    builds: list[BuildView]
    seconds: float


@dataclass(frozen=True)
class ShortfallView:
    reason: str | None
    lines: list[str]


@dataclass(frozen=True)
class FormOptions:
    stats: list[tuple[str, str, bool]]  # name, label, entered in %
    sets: list[tuple[int, str]]
    pools: list[tuple[str, str]]  # name, label; loosest first


@dataclass(frozen=True)
class SkillOption:
    """A skill to rank damage by; `note` describes its damage, or why it can't be ranked."""

    id: int
    name: str
    supported: bool
    note: str


@dataclass(frozen=True)
class ChampionPage:
    champion: ChampionRow
    current: list[StatCell]
    options: FormOptions
    skills: list[SkillOption]


def current_account() -> Account:
    """The latest capture; reparsed only when it changes (the proxy rewrites it often)."""
    return load_for(CAPTURES.joinpath("champions.json").stat().st_mtime_ns)


@lru_cache(maxsize=1)
def load_for(capture_mtime: int) -> Account:  # the mtime is only the cache key
    return load_account(CAPTURES, STATIC, SCHEMA)


def current_locks() -> Locks:
    return read_locks(STORE)


def lock_champion(champion: Champion, level: int) -> ListedChampion:
    """Locks the champion at `level` (0 unlocks them)."""
    write_lock(STORE, champion.id, level)
    return ListedChampion(champion_row(champion), level)


def search_champions(account: Account, locks: Locks, query: str) -> list[ListedChampion]:
    """Champions whose name contains `query`, most developed first."""
    wanted = query.casefold().strip()
    matches = [c for c in account.champions.values() if wanted in c.name.casefold()]
    matches.sort(key=lambda c: (-c.grade, -c.level, -(c.type_id % 10), c.name))
    return [ListedChampion(champion_row(c), locks.get(c.id, 0)) for c in matches[:SEARCH_LIMIT]]


def champion_row(champion: Champion) -> ChampionRow:
    return ChampionRow(
        id=champion.id,
        name=champion.name,
        rarity=champion.rarity,
        grade=champion.grade,
        level=champion.level,
        ascension=champion.type_id % 10,
        awakening=champion.awakening,
        empower=champion.empower,
        affinity=champion.element,
        faction=champion.faction,
        portrait_url=asset_url("portraits", str(champion.type_id // 10 * 10)),  # unascended
    )


def champion_page(account: Account, locks: Locks, champion: Champion) -> ChampionPage:
    return ChampionPage(
        champion=champion_row(champion),
        current=stat_cells(current_stats(account, champion), None),
        options=form_options(account, locks),
        skills=skill_options(account, champion),
    )


def skill_options(account: Account, champion: Champion) -> list[SkillOption]:
    options = []

    for skill_id in account.tables.hero_skills.get(champion.type_id, ()):
        skill = account.tables.skills.get(skill_id)
        if skill is None:
            continue

        match damage_goal(skill, champion, SUPPORT_CHECK_DEF):
            case Unsupported(reason=reason):
                options.append(SkillOption(skill.id, skill.name, False, reason))

            case goal:
                options.append(SkillOption(skill.id, skill.name, True, describe_goal(goal)))

    return options


def describe_goal(goal: DamageGoal) -> str:
    """ "4.5×ATK, AoE, ignores 15% DEF" """
    terms = [f"{k:g}×{STAT_LABELS[stat]}" for stat, k in goal.formula.coefficients.items()]

    if goal.formula.constant:
        terms.append(f"{goal.formula.constant:g}")

    extras = (["AoE"] if goal.aoe else []) + (
        [f"ignores {goal.skill_ignore * 100:g}% DEF"] if goal.skill_ignore else []
    )
    return ", ".join([" + ".join(terms), *extras])


def form_options(account: Account, locks: Locks) -> FormOptions:
    sets = sorted(
        ((set_id, s.name) for set_id, s in account.tables.sets.items() if s.name),
        key=lambda pair: pair[1],
    )
    return FormOptions(
        stats=[(stat.name, STAT_LABELS[stat], stat in PERCENT_STATS) for stat in Stat],
        sets=sets,
        pools=[(pool_name(pool), pool_label(pool)) for pool in pool_choices(locks)],
    )


def solve(account: Account, request: Request) -> ResultsView | ShortfallView:
    champion = request.champion
    started = time.monotonic()
    outcome = find_builds(account, request)
    seconds = time.monotonic() - started

    if isinstance(outcome, Shortfall):
        return shortfall_view(outcome, request)

    sets = account.tables.sets
    worn = current_gear(account, champion)
    current = build_stats(champion, worn, account.tables)
    goal = next((g for g in request.ranking if isinstance(g, DamageGoal)), None)
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
                n, build, current, account, champion, damage_cells(build.stats, build.artifacts)
            )
            for n, build in enumerate(outcome, 1)
        ],
        seconds=seconds,
    )


def current_stats(account: Account, champion: Champion) -> Stats:
    """The champion's stats in the gear they wear now."""
    return build_stats(champion, current_gear(account, champion), account.tables)


def current_gear(account: Account, champion: Champion) -> list[Artifact]:
    return [a for a in account.artifacts if a.id in set(champion.artifact_ids)]


def shortfall_view(shortfall: Shortfall, request: Request) -> ShortfallView:
    if shortfall.reason:
        return ShortfallView(shortfall.reason, [])

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
) -> BuildView:
    by_slot = {a.slot: piece_view(a, account, champion) for a in build.artifacts}
    pieces = list(by_slot.values())
    return BuildView(
        number=number,
        stats=stat_cells(build.stats, current) + extra_cells,
        slots=[by_slot.get(slot) for slot in SLOT_ORDER],
        artifact_ids=[artifact.id for artifact in build.artifacts],
        from_others=sum(1 for p in pieces if p.worn_by),
        equipped=sum(1 for p in pieces if p.equipped),
    )


def piece_view(artifact: Artifact, account: Account, champion: Champion) -> PieceView:
    artifact_set = account.tables.sets.get(artifact.set_id)
    owner_id = account.owners.get(artifact.id)
    owner = None if owner_id in (None, champion.id) else account.champions[owner_id]
    slot_key = artifact.slot.name.lower()

    return PieceView(
        id=artifact.id,
        slot="Amulet" if artifact.slot is Slot.AMULET else artifact.slot.value,
        set_name=artifact_set.name if artifact_set else "No set",
        set_icon_url=asset_url("sets", str(artifact.set_id)),
        # Set accessories share the set's art; only set-less ones show the faction's.
        image_url=asset_url("pieces", f"{artifact.set_id}_{slot_key}")
        or (asset_url("pieces", f"{artifact.faction}_{slot_key}") if artifact.faction else None),
        rank=artifact.rank,
        rarity=artifact.rarity,
        level=artifact.level,
        primary=line_view(artifact.primary),
        substats=[line_view(line) for line in artifact.substats],
        ascension=line_view(artifact.ascension) if artifact.ascension else None,
        faction=artifact.faction,
        worn_by=owner.name if owner else None,
        worn_by_portrait=champion_row(owner).portrait_url if owner else None,
        equipped=owner_id == champion.id,
    )


def line_view(line: StatLine) -> LineView:
    return LineView(
        label=line_label(line),
        amount=line_amount(line.value, line.absolute),
        glyph=f"+{line_amount(line.glyph, line.absolute)}" if line.glyph else None,
        rolls=line.rolls,
        optimised=line.stat is not None,
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


def asset_url(kind: str, key: str) -> str | None:
    """An extracted game icon, if we have it; pages fall back to text otherwise."""
    if ASSETS.joinpath(kind, f"{key}.png").is_file():
        return f"/static/assets/{kind}/{key}.png"

    return None
