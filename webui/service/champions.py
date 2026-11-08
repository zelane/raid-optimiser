"""
champions.py - the champion list and a champion's page: their stats now, the request
form's options, the skills damage can be ranked by, and their runs.

- `SEARCH_LIMIT`, `SUPPORT_CHECK_DEF`, `RARITY_ORDER`, `AFFINITY_ORDER`: the pages' shape, and
  the game's default champion order
- `ListedChampion`, `StatOption`, `SetOption`, `PoolOption`, `FormOptions`, `SkillOption`,
  `ChampionPage`: the views
- `search_champions`, `lock_champion`, `champion_page`: what the pages ask for
- `game_order`, `listed_champion`, `form_options`, `skill_options`, `describe_goal`,
  `current_stats`: what they share
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion, Locks, Stat, Stats, worn_gear
from optimiser.damage import DamageGoal, Unsupported, damage_goal
from optimiser.labels import PERCENT_STATS, STAT_LABELS, pool_choices, pool_label, pool_name
from optimiser.paths import STORE
from optimiser.stats import build_stats
from optimiser.store import latest_run, write_lock
from webui.service.results import StatCell, stat_cells
from webui.service.runs import RunEntryView, RunView, run_history, run_view
from webui.service.views import ChampionRow, champion_row

SEARCH_LIMIT = 200
SUPPORT_CHECK_DEF = 6000  # any DEF will do: whether a skill can be ranked doesn't depend on it
# The game's numbers for sorting: `HeroRarity`, and `ElementExtension.GetCompareToValue`.
RARITY_ORDER = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 5, "Mythical": 6}
AFFINITY_ORDER = {"Spirit": 1, "Magic": 2, "Force": 3, "Void": 4}


@dataclass(frozen=True)
class ListedChampion:
    """A champion on the champion list, with their lock (0: unlocked)."""

    champion: ChampionRow
    lock: int
    short_name: str  # the name's first word, for the grid


@dataclass(frozen=True)
class StatOption:
    name: str  # `Stat` member name, as the form's fields use it
    label: str
    percent: bool  # entered in %


@dataclass(frozen=True)
class SetOption:
    id: int
    name: str


@dataclass(frozen=True)
class PoolOption:
    name: str  # `pool_name`
    label: str


@dataclass(frozen=True)
class FormOptions:
    stats: list[StatOption]
    sets: list[SetOption]  # by name
    pools: list[PoolOption]  # loosest first


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
    history: list[RunEntryView]
    latest: RunView | None  # shown, and its form restored, when the page opens


def search_champions(account: Account, locks: Locks, query: str) -> list[ListedChampion]:
    """Champions whose name contains `query`, in the game's default order."""
    wanted = query.casefold().strip()
    matches = [c for c in account.champions.values() if wanted in c.name.casefold()]
    matches.sort(key=game_order, reverse=True)
    return [listed_champion(c, locks.get(c.id, 0)) for c in matches[:SEARCH_LIMIT]]


def lock_champion(champion: Champion, level: int) -> ListedChampion:
    """Locks the champion at `level` (0 unlocks them)."""
    write_lock(STORE, champion.id, level)
    return listed_champion(champion, level)


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


def game_order(champion: Champion) -> tuple[int, ...]:
    """The champion list's default sort ("Rank", descending; `HeroAvatarComparator.
    CompareByRank`, negated): each key high to low, so the newest copy comes first."""
    return (
        champion.grade,
        champion.level,
        champion.ascension,
        RARITY_ORDER.get(champion.rarity, 0),
        champion.empower,
        champion.awakening,
        AFFINITY_ORDER.get(champion.element, 0),
        champion.type_id,
        champion.id,
    )


def listed_champion(champion: Champion, lock: int) -> ListedChampion:
    return ListedChampion(champion_row(champion), lock, champion.name.split()[0])


def form_options(account: Account, locks: Locks) -> FormOptions:
    sets = sorted(
        (SetOption(set_id, s.name) for set_id, s in account.tables.sets.items() if s.name),
        key=lambda option: option.name,
    )
    return FormOptions(
        stats=[StatOption(stat.name, STAT_LABELS[stat], stat in PERCENT_STATS) for stat in Stat],
        sets=sets,
        pools=[PoolOption(pool_name(pool), pool_label(pool)) for pool in pool_choices(locks)],
    )


def skill_options(account: Account, champion: Champion) -> list[SkillOption]:
    options = []

    for skill_id in account.tables.skills_of(champion.type_id):
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


def current_stats(account: Account, champion: Champion) -> Stats:
    """The champion's stats in the gear they wear now."""
    return build_stats(champion, worn_gear(account, champion), account.tables)
