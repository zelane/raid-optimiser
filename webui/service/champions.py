"""
champions.py - a champion's page: in each of their forms, their stats now and the skills
damage can be ranked by; the request form's options; and their runs. The champion list is
the finder's (`service.finder`).

- `SUPPORT_CHECK_DEF`, `RARITY_ORDER`, `AFFINITY_ORDER`: the page's shape, and the game's
  default champion order
- `StatOption`, `SetOption`, `RuleOption`, `BattleOption`, `BattleGroup`, `BattleOptions`,
  `FormOptions`, `SkillOption`, `FormView`, `ChampionPage`: the views
- `champion_page`, `shown_run`: what the page asks for
- `game_order`, `form_options`, `battle_options` (`buff_groups`, `buff_option`, `aura_groups`,
  `aura_option`), `form_views`,
  `skill_options`, `describe_goal`, `current_stats`: what it shares
"""

from dataclasses import dataclass, replace

from optimiser.account import LOCK_LEVELS, Account, Champion, worn_gear
from optimiser.battle import BUFFS, Buff, Leader, auras_reaching
from optimiser.damage import DamageGoal, Unsupported, damage_goal
from optimiser.labels import (
    PERCENT_STATS,
    STAT_LABELS,
    aura_holds,
    aura_label,
    buff_label,
    rule_label,
)
from optimiser.paths import STORE
from optimiser.reserve import Rule, reservations, reserved_count, rule_key
from optimiser.stats import build_stats
from optimiser.store import latest_run
from optimiser.tables import Stat, Stats
from webui.service.results import StatCell, stat_cells
from webui.service.runs import RunEntryView, RunView, run_history, run_view, saved_run
from webui.service.skills import SkillLevel, form_skills
from webui.service.team import IconView
from webui.service.views import ChampionRow, asset_url, champion_row

SUPPORT_CHECK_DEF = 6000  # any DEF will do: whether a skill can be ranked doesn't depend on it
# The game's numbers for sorting: `HeroRarity`, and `ElementExtension.GetCompareToValue`.
RARITY_ORDER = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 5, "Mythical": 6}
AFFINITY_ORDER = {"Spirit": 1, "Magic": 2, "Force": 3, "Void": 4}


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
class BattleOption:
    """A buff or a leader's aura to assume, as the page's picker lists it. `field` and `value`
    are the form's (`buff_SPD` and "30"; `aura` and a `Leader.key`)."""

    field: str
    value: str
    label: str
    note: str | None
    icons: list[IconView]


@dataclass(frozen=True)
class BattleGroup:
    title: str
    options: list[BattleOption]


@dataclass(frozen=True)
class BattleOptions:
    """Buffs by stat; the auras reaching the champion by stat, strongest first."""

    buffs: list[BattleGroup]
    auras: list[BattleGroup]


@dataclass(frozen=True)
class FormOptions:
    stats: list[StatOption]
    sets: list[SetOption]  # by name
    rules: list[RuleOption]  # the reserve rules, as configured
    lock_levels: list[int]  # for "only from champions locked up to": 0 (unlocked) first
    battle: BattleOptions


@dataclass(frozen=True)
class SkillOption:
    """A skill to rank damage by; `note` describes its damage, or why it can't be ranked."""

    id: int
    name: str
    supported: bool
    note: str


@dataclass(frozen=True)
class FormView:
    """One of the champion's forms (most have only one): its stats in the gear worn now, its
    skills and how far each is booked, and the skills damage can be ranked by in it. `icon_url`
    is its helm when picked, `idle_url` when not (None without the art; mythicals' two forms
    have it)."""

    number: int  # 0 first, as the request's `form` field posts it
    role: str  # the game's: Attack, Defense, Health, Support
    icon_url: str | None
    idle_url: str | None
    current: list[StatCell]
    books: list[SkillLevel]
    skills: list[SkillOption]


@dataclass(frozen=True)
class ChampionPage:
    """`forms`: one per form, the first first; a toggle on the page picks between them. The
    run shown (`shown_run`) is the page's other prop: picking one from the history reloads it
    alone."""

    champion: ChampionRow
    forms: list[FormView]
    options: FormOptions
    history: list[RunEntryView]


def champion_page(account: Account, rules: tuple[Rule, ...], champion: Champion) -> ChampionPage:
    return ChampionPage(
        champion=champion_row(champion),
        forms=form_views(account, champion),
        options=form_options(account, rules, champion),
        history=run_history(champion),
    )


def shown_run(champion: Champion, run_id: int | None) -> RunView | None:
    """The run asked for, else (none asked, or it's gone) the latest; its form is restored."""
    if run_id is not None and (asked := saved_run(champion, run_id)) is not None:
        return asked

    latest = latest_run(STORE, champion.id)
    return run_view(latest, champion) if latest else None


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


def form_options(account: Account, rules: tuple[Rule, ...], champion: Champion) -> FormOptions:
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
        battle=battle_options(account, champion),
    )


def battle_options(account: Account, champion: Champion) -> BattleOptions:
    return BattleOptions(buffs=buff_groups(), auras=aura_groups(account, champion))


def buff_groups() -> list[BattleGroup]:
    """A group per stat, its two strengths (the stronger with the game's second icon)."""
    return [
        BattleGroup(
            STAT_LABELS[stat],
            [
                buff_option(buff, f"StatusIncrease{stat.value}{suffix}")
                for buff, suffix in zip(strengths, ("", "2"), strict=True)
            ],
        )
        for stat, strengths in BUFFS.items()
    ]


def buff_option(buff: Buff, icon: str) -> BattleOption:
    label = buff_label(buff)
    return BattleOption(
        field=f"buff_{buff.stat.name}",
        value=str(buff.percent),
        label=label,
        note=None,
        icons=[IconView(label, asset_url("statuses", icon))],
    )


def aura_groups(account: Account, champion: Champion) -> list[BattleGroup]:
    leaders = auras_reaching(account, champion)
    groups = []

    for stat in Stat:
        held = [leader for leader in leaders if leader.aura.bonus.stat == stat]
        held.sort(key=lambda leader: (-leader.aura.bonus.value, leader.champion.name))

        if held:
            groups.append(
                BattleGroup(STAT_LABELS[stat], [aura_option(account, each) for each in held])
            )

    return groups


def aura_option(account: Account, leader: Leader) -> BattleOption:
    """A mythical's aura is one of its forms': it says which."""
    name = leader.champion.name
    forms = len(account.tables.hero_types[leader.champion.type_id].auras)
    return BattleOption(
        field="aura",
        value=leader.key,
        label=f"{name} (form {leader.number + 1})" if forms > 1 else name,
        note=" · ".join(filter(None, [aura_label(leader.aura), aura_holds(leader.aura)])),
        icons=[IconView(name, champion_row(leader.champion).portrait_url)],
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
                books=form_skills(form, champion.skill_levels, account.tables),
                skills=skill_options(account, in_form),
            )
        )

    return views


def skill_options(account: Account, champion: Champion) -> list[SkillOption]:
    options = []

    for skill_id in champion.skills_in(account.tables):
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
