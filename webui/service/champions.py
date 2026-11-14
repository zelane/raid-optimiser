"""
champions.py - the champion list and a champion's page: in each of their forms, their stats
now and the skills damage can be ranked by; the request form's options; and their runs.

- `SEARCH_LIMIT`, `SUPPORT_CHECK_DEF`, `RARITY_ORDER`, `AFFINITY_ORDER`: the pages' shape, and
  the game's default champion order
- `ListedChampion`, `StatOption`, `SetOption`, `RuleOption`, `FormOptions`, `SkillOption`,
  `FormView`, `ChampionPage`: the views
- `search_champions`, `lock_champion`, `champion_page`: what the pages ask for
- `game_order`, `listed_champion`, `form_options`, `form_views`, `skill_options`,
  `describe_goal`, `current_stats`: what they share
"""

from dataclasses import dataclass, replace

from optimiser.account import LOCK_LEVELS, Account, Champion, Locks, Stat, Stats, worn_gear
from optimiser.damage import DamageGoal, Unsupported, damage_goal
from optimiser.labels import PERCENT_STATS, STAT_LABELS, rule_label
from optimiser.paths import STORE
from optimiser.reserve import Rule, reservations, reserved_count, rule_key
from optimiser.stats import build_stats
from optimiser.store import latest_run, write_lock
from webui.service.results import StatCell, stat_cells
from webui.service.runs import RunEntryView, RunView, run_history, run_view
from webui.service.views import ChampionRow, asset_url, champion_row

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


@dataclass(frozen=True)
class StatOption:
    name: str  # `Stat` member name, as the form's fields use it
    label: str
    percent: bool  # entered in %


@dataclass(frozen=True)
class SetOption:
    id: int
    name: str
    icon_url: str | None


@dataclass(frozen=True)
class RuleOption:
    """A reserve rule a solve can keep out (the form's `exclude_<key>`, on by default)."""

    key: str  # `rule_key`
    label: str
    pieces: int  # how many it reserves


@dataclass(frozen=True)
class FormOptions:
    stats: list[StatOption]
    sets: list[SetOption]  # by name
    rules: list[RuleOption]  # the reserve rules, as configured
    lock_levels: list[int]  # for "only from champions locked up to": 0 (unlocked) first


@dataclass(frozen=True)
class SkillOption:
    """A skill to rank damage by; `note` describes its damage, or why it can't be ranked."""

    id: int
    name: str
    supported: bool
    note: str


@dataclass(frozen=True)
class FormView:
    """One of the champion's forms (most have only one): its stats in the gear worn now, and
    the skills damage can be ranked by in it. `icon_url` is its helm when picked, `idle_url`
    when not (None without the art; mythicals' two forms have it)."""

    number: int  # 0 first, as the request's `form` field posts it
    role: str  # the game's: Attack, Defense, Health, Support
    icon_url: str | None
    idle_url: str | None
    current: list[StatCell]
    skills: list[SkillOption]


@dataclass(frozen=True)
class ChampionPage:
    """`forms`: one per form, the first first; a toggle on the page picks between them."""

    champion: ChampionRow
    forms: list[FormView]
    options: FormOptions
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


def champion_page(account: Account, rules: tuple[Rule, ...], champion: Champion) -> ChampionPage:
    latest = latest_run(STORE, champion.id)
    return ChampionPage(
        champion=champion_row(champion),
        forms=form_views(account, champion),
        options=form_options(account, rules),
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
    return ListedChampion(champion_row(champion), lock)


def form_options(account: Account, rules: tuple[Rule, ...]) -> FormOptions:
    """Up to the top lock level would let any locked champion's gear in, so it's left out."""
    sets = sorted(
        (
            SetOption(set_id, s.name, asset_url("sets", str(set_id)))
            for set_id, s in account.tables.sets.items()
            if s.name
        ),
        key=lambda option: option.name,
    )
    reserved = reservations(account, rules)
    return FormOptions(
        stats=[StatOption(stat.name, STAT_LABELS[stat], stat in PERCENT_STATS) for stat in Stat],
        sets=sets,
        rules=[
            RuleOption(
                rule_key(rule),
                rule_label(rule, account),
                reserved_count(reserved, rule),
            )
            for rule in rules
        ],
        lock_levels=list(range(max(LOCK_LEVELS))),
    )


def form_views(account: Account, champion: Champion) -> list[FormView]:
    forms = account.tables.hero_forms.get(champion.type_id) or ()
    views = []

    for number, form in enumerate(forms):
        in_form = replace(champion, form=number)
        views.append(
            FormView(
                number=number,
                role=form.role,
                icon_url=asset_url("forms", str(number + 1)),
                idle_url=asset_url("forms", f"{number + 1}-white"),
                current=stat_cells(current_stats(account, in_form), None),
                skills=skill_options(account, in_form),
            )
        )

    return views


def skill_options(account: Account, champion: Champion) -> list[SkillOption]:
    options = []

    for skill_id in account.tables.skills_of(champion):
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
