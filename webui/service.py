"""
service.py - what the web pages show, as plain data: no HTML and no web framework, so a JSON
API (for a Vue front end, say) can return the same objects with `dataclasses.asdict`.

- `StarView`, `ChampionRow`, `ListedChampion`, `StatCell`, `LineView`, `PieceView`,
  `BuildView`: the views
- `SkillOption`, `ResultsView`, `ShortfallView`, `Outcome`, `FormOptions`, `RunEntryView`,
  `RunView`, `ChampionPage`: what a page is made of
- `current_account`: the account, reloaded when a new capture lands
- `current_locks`, `lock_champion`: champion locks, kept in the store
- `FlagView`, `AssumptionsPage`, `assumptions_page`, `flag_view`, `set_assumption`,
  `GlyphChoice`, `GlyphRow`, `glyph_row`, `plan_glyph_for`: what solves
  assume (top levels, full ascension, glyphs), kept in the store
- `record_run`, `run_history`, `saved_run`, `forget_run`: a champion's runs, kept in the store
- `search_champions`, `champion_page`, `solve`: what the pages ask for
- `RARITY_ORDER`, `AFFINITY_ORDER`, `game_order`: the game's default champion order
- `describe_request`, `describe_ranked`, `outcome_note`, `outcome_json`, `revive_outcome`,
  `revive`, `revive_value`, `run_view`, `entry_view`: what runs share
- `load_for`, `listed_champion`, `champion_row`, `star_colour`, `form_options`, `skill_options`,
  `current_stats`, `current_gear`, `shortfall_view`, `build_view`, `piece_view`, `line_view`,
  `stat_cells`, `damage_cell`, `describe_goal`, `asset_url`: what they share
"""

import time
import types
import typing
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from optimiser.account import (
    Account,
    Artifact,
    Champion,
    GlyphGrade,
    GlyphKind,
    Slot,
    Stat,
    StatLine,
    Stats,
    load_account,
)
from optimiser.assume import FLAG_LABELS, Flag, assume, read_assumptions, set_flag
from optimiser.damage import DamageGoal, Unsupported, damage_goal, estimate_damage
from optimiser.glyphs import grade_key, kind_key, plan_glyph
from optimiser.labels import (
    PERCENT_STATS,
    STAT_LABELS,
    format_stat,
    glyph_grade_label,
    glyph_kind_label,
    line_amount,
    line_label,
    pool_choices,
    pool_label,
    pool_name,
)
from optimiser.solve import Build, Goal, Request, Shortfall, find_builds
from optimiser.stats import build_stats, set_multiplier
from optimiser.store import (
    Locks,
    NewRun,
    Run,
    RunEntry,
    delete_run,
    latest_run,
    list_runs,
    read_locks,
    read_run,
    save_run,
    write_lock,
)

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "captures" / "latest"
STATIC = ROOT / "static"
SCHEMA = ROOT / "schema" / "schema.json"
STORE = ROOT / "state" / "optimiser.sqlite"
ASSETS = Path(__file__).resolve().parent / "static" / "assets"
SLOT_ORDER = list(Slot)
SEARCH_LIMIT = 200
HISTORY_LIMIT = 30  # runs listed per champion
SUPPORT_CHECK_DEF = 6000
# The game's numbers for sorting: `HeroRarity`, and `ElementExtension.GetCompareToValue`.
RARITY_ORDER = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 5, "Mythical": 6}
AFFINITY_ORDER = {
    "Spirit": 1,
    "Magic": 2,
    "Force": 3,
    "Void": 4,
}  # any DEF will do: whether a skill can be ranked doesn't depend on it


@dataclass(frozen=True)
class StarView:
    colour: str  # "red" awakened, "purple" ascended, "yellow" neither
    image_url: str | None


@dataclass(frozen=True)
class ChampionRow:
    """The defaults are for runs saved before those fields existed."""

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
    stars: list[StarView] = field(default_factory=list)
    affinity_icon_url: str | None = None
    faction_icon_url: str | None = None


@dataclass(frozen=True)
class ListedChampion:
    """A champion on the champion list, with their lock (0: unlocked)."""

    champion: ChampionRow
    lock: int
    short_name: str  # the name's first word, for the grid


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
class FlagView:
    name: str
    label: str
    on: bool


@dataclass(frozen=True)
class GlyphChoice:
    key: str  # `grade_key`; "" for none
    label: str  # "6★ Legendary (+12)"


@dataclass(frozen=True)
class GlyphRow:
    """A glyph kind and the grade assumed for it ("" for none)."""

    key: str  # `kind_key`
    label: str
    choices: list[GlyphChoice]
    chosen: str


@dataclass(frozen=True)
class AssumptionsPage:
    flags: list[FlagView]
    glyphs: list[GlyphRow]


@dataclass(frozen=True)
class ShortfallView:
    reason: str | None
    lines: list[str]


type Outcome = ResultsView | ShortfallView


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
class RunEntryView:
    id: int
    ran_at: str  # local time, "08 Nov 14:03"
    summary: str
    note: str


@dataclass(frozen=True)
class RunView:
    """A saved run. `outcome` is None when it was saved in a shape these views no longer
    have."""

    entry: RunEntryView
    form: dict[str, str]
    outcome: Outcome | None


@dataclass(frozen=True)
class ChampionPage:
    champion: ChampionRow
    current: list[StatCell]
    options: FormOptions
    skills: list[SkillOption]
    history: list[RunEntryView]
    latest: RunView | None  # shown, and its form restored, when the page opens


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
    return listed_champion(champion, level)


def assumptions_page(account: Account) -> AssumptionsPage:
    assumptions = read_assumptions(STORE, account)
    planned = assumptions.glyphs
    return AssumptionsPage(
        flags=[flag_view(flag, flag in assumptions.flags) for flag in Flag],
        glyphs=[glyph_row(account, kind, planned.get(kind)) for kind in account.tables.glyphs],
    )


def flag_view(flag: Flag, on: bool) -> FlagView:
    return FlagView(flag.value, FLAG_LABELS[flag], on)


def set_assumption(flag: Flag, on: bool) -> FlagView:
    set_flag(STORE, flag, on)
    return flag_view(flag, on)


def glyph_row(account: Account, kind: GlyphKind, chosen: GlyphGrade | None) -> GlyphRow:
    tops = account.tables.glyphs[kind]
    choices = [
        GlyphChoice(
            grade_key(grade), f"{glyph_grade_label(grade)} (+{line_amount(top, kind.absolute)})"
        )
        for grade, top in reversed(tops.items())
    ]
    return GlyphRow(
        key=kind_key(kind),
        label=glyph_kind_label(kind),
        choices=[GlyphChoice("", "None"), *choices],
        chosen=grade_key(chosen) if chosen else "",
    )


def plan_glyph_for(account: Account, kind: GlyphKind, grade: GlyphGrade | None) -> GlyphRow:
    """None stops assuming the kind."""
    plan_glyph(STORE, kind, grade)
    return glyph_row(account, kind, grade)


def record_run(
    account: Account, form: dict[str, str], request: Request, outcome: Outcome
) -> RunView:
    run = NewRun(
        champion_id=request.champion.id,
        summary=describe_request(request, account),
        note=outcome_note(outcome),
        form=form,
        outcome=outcome_json(outcome),
    )
    return run_view(save_run(STORE, run, datetime.now(UTC)), request.champion)


def run_history(champion: Champion) -> list[RunEntryView]:
    """Newest first."""
    return [entry_view(entry) for entry in list_runs(STORE, champion.id, HISTORY_LIMIT)]


def saved_run(champion: Champion, run_id: int) -> RunView | None:
    """None when the champion has no such run."""
    run = read_run(STORE, champion.id, run_id)
    return run_view(run, champion) if run else None


def forget_run(champion: Champion, run_id: int) -> None:
    delete_run(STORE, champion.id, run_id)


def search_champions(account: Account, locks: Locks, query: str) -> list[ListedChampion]:
    """Champions whose name contains `query`, in the game's default order."""
    wanted = query.casefold().strip()
    matches = [c for c in account.champions.values() if wanted in c.name.casefold()]
    matches.sort(key=game_order, reverse=True)
    return [listed_champion(c, locks.get(c.id, 0)) for c in matches[:SEARCH_LIMIT]]


def listed_champion(champion: Champion, lock: int) -> ListedChampion:
    return ListedChampion(champion_row(champion), lock, champion.name.split()[0])


def champion_row(champion: Champion) -> ChampionRow:
    ascension = champion.type_id % 10
    colours = [star_colour(star, ascension, champion.awakening) for star in range(champion.grade)]

    return ChampionRow(
        id=champion.id,
        name=champion.name,
        rarity=champion.rarity,
        grade=champion.grade,
        level=champion.level,
        ascension=ascension,
        awakening=champion.awakening,
        empower=champion.empower,
        affinity=champion.element,
        faction=champion.faction,
        portrait_url=asset_url("portraits", str(champion.type_id // 10 * 10)),  # unascended
        stars=[StarView(colour, asset_url("stars", colour)) for colour in colours],
        affinity_icon_url=asset_url("affinities", champion.element.lower()),
        faction_icon_url=asset_url("factions", champion.faction),
    )


def star_colour(star: int, ascension: int, awakening: int) -> str:
    """Counting from the first star: awakened ones, then ascended ones, then plain (a
    champion is never awakened past their ascension)."""
    if star < awakening:
        return "red"

    if star < ascension:
        return "purple"

    return "yellow"


def game_order(champion: Champion) -> tuple[int, ...]:
    """The champion list's default sort ("Rank", descending; `HeroAvatarComparator.
    CompareByRank`, negated): each key high to low, so the newest copy comes first."""
    return (
        champion.grade,
        champion.level,
        champion.type_id % 10,  # ascension
        RARITY_ORDER.get(champion.rarity, 0),
        champion.empower,
        champion.awakening,
        AFFINITY_ORDER.get(champion.element, 0),
        champion.type_id,
        champion.id,
    )


def champion_page(account: Account, locks: Locks, champion: Champion) -> ChampionPage:
    latest = latest_run(STORE, champion.id)
    return ChampionPage(
        champion=champion_row(champion),
        current=stat_cells(current_stats(account, champion), None),
        options=form_options(account, locks),
        skills=skill_options(account, champion),
        history=run_history(champion),
        latest=run_view(latest, champion) if latest else None,
    )


def describe_request(request: Request, account: Account) -> str:
    """ "HP › SPD · SPD ≥ 200 · Lethal 4 · gear: Locked up to 2" """
    at_least = [
        f"{STAT_LABELS[stat]} ≥ {format_stat(stat, value)}"
        for stat, value in request.minimums.items()
    ]
    at_most = [
        f"{STAT_LABELS[stat]} ≤ {format_stat(stat, value)}"
        for stat, value in request.maximums.items()
    ]
    sets = [
        f"{account.tables.sets[set_id].name} {pieces}"
        for set_id, pieces in request.set_minimums.items()
    ]
    ranking = " › ".join(describe_ranked(goal) for goal in request.ranking)
    return " · ".join([ranking, *at_least, *at_most, *sets, f"gear: {pool_label(request.pool)}"])


def describe_ranked(goal: Goal) -> str:
    match goal:
        case DamageGoal(skill_name=skill_name):
            return f"{skill_name} DMG"

        case stat:
            return STAT_LABELS[stat]


def outcome_note(outcome: Outcome) -> str:
    match outcome:
        case ResultsView(builds=builds):
            return f"{len(builds)} build{'s' if len(builds) != 1 else ''}"

        case ShortfallView():
            return "no build"


def outcome_json(outcome: Outcome) -> dict:
    return {"kind": type(outcome).__name__, "view": asdict(outcome)}


def revive_outcome(saved: dict) -> Outcome | None:
    """The outcome `outcome_json` saved, or None if the views have changed shape since."""
    kinds = {"ResultsView": ResultsView, "ShortfallView": ShortfallView}

    try:
        return revive(kinds[saved["kind"]], saved["view"])
    except (KeyError, TypeError, ValueError):
        return None


def revive[T](cls: type[T], data: dict) -> T:
    """A view `asdict` saved, rebuilt with its nested views; raises on fields that don't
    fit."""
    hints = typing.get_type_hints(cls)
    return cls(**{name: revive_value(hints[name], value) for name, value in data.items()})


def revive_value(hint: object, value: object) -> object:
    origin = typing.get_origin(hint)

    if value is None:
        return None

    if origin in (typing.Union, types.UnionType):
        (inner,) = [arm for arm in typing.get_args(hint) if arm is not type(None)]
        return revive_value(inner, value)

    if origin is list and isinstance(value, list):
        (item_hint,) = typing.get_args(hint)
        return [revive_value(item_hint, item) for item in value]

    if isinstance(hint, type) and is_dataclass(hint) and isinstance(value, dict):
        return revive(hint, value)

    return value


def run_view(run: Run, champion: Champion) -> RunView:
    """Results show the champion as they are now (a portrait extracted since, say)."""
    match revive_outcome(run.outcome):
        case ResultsView() as results:
            outcome = replace(results, champion=champion_row(champion))

        case other:
            outcome = other

    return RunView(entry_view(run.entry), run.form, outcome)


def entry_view(entry: RunEntry) -> RunEntryView:
    ran_at = entry.ran_at.astimezone().strftime("%d %b %H:%M")
    return RunEntryView(entry.id, ran_at, entry.summary, entry.note)


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


def solve(account: Account, request: Request) -> Outcome:
    assumed, request = assume(account, request, read_assumptions(STORE, account))
    champion = request.champion
    started = time.monotonic()
    outcome = find_builds(assumed, request)
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
        champion_level_note=(
            f"at L{champion.level} (now L{account.champions[champion.id].level})"
            if champion.level != account.champions[champion.id].level
            else None
        ),
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
        glyphs_to_apply=sum(1 for p in pieces for line in p.substats if line.planned_glyph),
        to_level=sum(1 for p in pieces if p.planned_level),
        to_ascend=sum(1 for p in pieces if p.planned_ascend_level),
    )


def piece_view(artifact: Artifact, account: Account, champion: Champion) -> PieceView:
    artifact_set = account.tables.sets.get(artifact.set_id)
    owner_id = account.owners.get(artifact.id)
    wearer = account.champions.get(owner_id) if owner_id is not None else None
    owner = None if owner_id == champion.id else wearer
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
        stars=[
            StarView(colour, asset_url("stars", colour))
            for colour in (
                star_colour(star, artifact.ascend_level, 0) for star in range(artifact.rank)
            )
        ],
        ascend_level=artifact.ascend_level,
        planned_level=artifact.planned_level,
        planned_ascend_level=artifact.planned_ascend_level,
        faction=artifact.faction,
        worn_by=owner.name if owner else None,
        worn_by_portrait=champion_row(wearer).portrait_url if wearer else None,
        equipped=owner_id == champion.id,
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


def asset_url(kind: str, key: str) -> str | None:
    """An extracted game icon, if we have it; pages fall back to text otherwise."""
    if ASSETS.joinpath(kind, f"{key}.png").is_file():
        return f"/static/assets/{kind}/{key}.png"

    return None
