"""
team_gear.py - the team gear page: up to five champions geared at once against one target,
each with a compact row (sets, SPD, ACC and C.RATE minimums, one goal to rank), the first
champion's goal ranked first. No piece goes to two of them (`solve.find_team_builds`).

- `SetPickView`, `MinimumView`, `RowView`, `RuleView`, `MemberResult`, `TeamResult`,
  `TeamShortfall`, `GearPage`: the views
- `RANK_CHOICES`: what a row can rank
- `gear_page`: the workflow
- `slot_view`, `row_view`, `minimum_view`, `minimum_value`, `places_debuffs`,
  `damage_skills`, `default_skill`, `solve_team`, `row_goal`, `member_request`, `member_result`,
  `shortfall_lines`, `percent`: its steps
"""

import time
from dataclasses import dataclass, replace

from optimiser.account import Account, Champion, worn_gear
from optimiser.accuracy import (
    Lands,
    Resists,
    accuracy_for_floor,
    resist_chance,
    resistance_for_cap,
)
from optimiser.assume import assume
from optimiser.damage import DamageGoal, Unsupported, damage_goal, estimate_damage
from optimiser.enemies import Restriction, Rotating
from optimiser.labels import STAT_LABELS, format_stat, rule_label
from optimiser.paths import STORE
from optimiser.reserve import Reservations, Rule, reservations, rule_key
from optimiser.settings import read_assumptions
from optimiser.solve import (
    Build,
    Clash,
    Goal,
    Member,
    Request,
    SetsRuleOut,
    Shortfall,
    Stopped,
    Unmet,
    find_team_builds,
)
from optimiser.stats import build_stats
from optimiser.tables import Stat
from optimiser.teams.kits import kit_of
from optimiser.teams.tags import Side
from webui.forms.request import DEFAULT_ABOVE_LEVEL, RATE_GOALS, exclude_field, filter_form
from webui.forms.team import Unmatched
from webui.forms.team_gear import (
    DAMAGE,
    PAGE_FIELDS,
    ROW_MINIMUMS,
    SETS_PER_ROW,
    Default,
    GearAsk,
    Minimum,
    PageFields,
    RowAsk,
    RowFields,
    minimum_field,
    row_fields,
)
from webui.service.finder import restriction_label
from webui.service.results import BuildView, StatCell, build_view, damage_cell, stat_cells
from webui.service.targets import EnemyCard
from webui.service.team import ChoiceView, SlotView
from webui.service.views import ChampionRow, champion_row, choice_label, slot_value

RANK_CHOICES = (Stat.SPD, Stat.HP, Stat.DEF, Stat.ATK, Stat.RES, Stat.ACC)
SLACK = 0.01


@dataclass(frozen=True)
class SetPickView:
    set_id: int | None  # None: no set picked
    pieces: int | None


@dataclass(frozen=True)
class MinimumView:
    """A minimum's field: its value as typed (or the default), and where the default came
    from."""

    field: str
    label: str
    value: str
    note: str | None
    placeholder: str = ""  # what to type for the most it can do (RES: near the cap)


@dataclass(frozen=True)
class RowView:
    """A placed champion's row: `number` is its slot (1 first); `fields`, its fields' names."""

    number: int
    fields: RowFields
    champion: ChampionRow
    sets: list[SetPickView]
    minimums: list[MinimumView]
    rank: str  # a `Stat` name or `DAMAGE`
    skills: list[tuple[int, str]]  # skills whose damage can be ranked: id, name
    skill: int | None
    refused: bool = False  # the target's stage doesn't admit them


@dataclass(frozen=True)
class RuleView:
    """A reserve rule the solve can keep out: `field` is its switch's name."""

    key: str
    field: str
    label: str
    on: bool


@dataclass(frozen=True)
class MemberResult:
    """A champion's build, as the champion page's build details draw it (`champion`, `build`),
    with the stats now (`current`) and what the DMG column measures."""

    champion: ChampionRow
    current: list[StatCell]
    build: BuildView
    damage: str | None
    resisted: str  # how often the target resists the build's debuffs, "3.1%"
    resists: str  # how often the build resists the target's debuffs


@dataclass(frozen=True)
class TeamResult:
    """`gear`: the gear rules it was found under, and `team` its champions' ids, which each
    member's Equip sends to be checked again (teammates' pieces are fair game)."""

    members: list[MemberResult]
    seconds: float
    gear: dict[str, str]
    team: list[int]


@dataclass(frozen=True)
class TeamShortfall:
    """No team build: who can't be geared alone and why (`lines` per champion), or that each
    can but not together (`clash`)."""

    clash: bool
    members: list[tuple[ChampionRow, list[str]]]


@dataclass(frozen=True)
class GearPage:
    slots: list[SlotView]
    choices: list[ChoiceView]
    rows: list[RowView]
    sets: list[tuple[int, str]]  # every set: id, name
    ranks: list[tuple[str, str]]  # value, label
    rules: list[RuleView]
    unworn_only: bool
    resistance: int  # the target's, which the ACC defaults follow (`res`)
    fields: PageFields  # the query's own names
    damage_rank: str  # the rank that ranks a skill's damage (with its skill field)
    target_note: str
    admits: str | None  # what the target's stage admits, in words ("Magic champions")
    rotating: bool  # the stage's restriction rotates, unknown which is active
    result: TeamResult | None
    shortfall: TeamShortfall | None
    stopped: bool  # the solve was stopped (`/stop`) before it found the team's gear


def gear_page(
    account: Account,
    ask: GearAsk,
    rules: tuple[Rule, ...],
    target: EnemyCard,
    title: str,
    restriction: Restriction | Rotating | None,
) -> GearPage:
    """`target`: the enemy picked (its DEF for damage, its RES for ACC); `restriction`: what
    its stage admits."""
    champions = sorted(account.champions.values(), key=lambda c: (c.name, -c.grade, -c.level))
    placed = [(slot, pick) for slot, pick in enumerate(ask.picks, 1) if isinstance(pick, Champion)]
    rows = [row_view(account, slot, pick, ask.rows[slot - 1], ask, target) for slot, pick in placed]

    if isinstance(restriction, Restriction):
        rows = [
            replace(row, refused=not restriction.admits(pick))
            for row, (_, pick) in zip(rows, placed, strict=True)
        ]

    # Solve only when asked: a run takes seconds.
    outcome = None

    if ask.run and placed:
        outcome = solve_team(account, ask, [pick for _, pick in placed], rows, target)

    return GearPage(
        slots=[slot_view(pick) for pick in ask.picks],
        choices=[ChoiceView(choice_label(c)) for c in champions],
        rows=rows,
        sets=sorted(((s.id, s.name) for s in account.tables.sets.values()), key=lambda s: s[1]),
        ranks=[(stat.name, STAT_LABELS[stat]) for stat in RANK_CHOICES]
        + [(DAMAGE, "Damage")]
        + list(RATE_GOALS.items()),
        rules=[
            RuleView(
                rule_key(rule),
                exclude_field(rule),
                rule_label(rule, account),
                rule in ask.gear.rules,
            )
            for rule in rules
        ],
        unworn_only=ask.gear.unworn_only,
        resistance=target.resistance,
        fields=PAGE_FIELDS,
        damage_rank=DAMAGE,
        target_note=f"{title if title.startswith(target.name) else f'{target.name}, {title}'}: "
        f"{target.resistance} RES, {target.accuracy} ACC, {target.speed} SPD, {target.defence} DEF",
        admits=restriction_label(restriction) if isinstance(restriction, Restriction) else None,
        rotating=isinstance(restriction, Rotating),
        result=outcome if isinstance(outcome, TeamResult) else None,
        shortfall=outcome if isinstance(outcome, TeamShortfall) else None,
        stopped=isinstance(outcome, Stopped),
    )


def slot_view(pick) -> SlotView:
    match pick:
        case Champion() as champion:
            return SlotView(champion_row(champion), slot_value(champion), False, False)
        case Unmatched(text=text, reason=reason):
            return SlotView(None, text, False, False, problem=reason)
        case _:
            return SlotView(None, "", False, False)


def row_view(
    account: Account, slot: int, champion: Champion, row: RowAsk, ask: GearAsk, target: EnemyCard
) -> RowView:
    picks = [SetPickView(set_id, pieces) for set_id, pieces in row.sets.items()]
    skills = damage_skills(account, champion, target.defence)
    return RowView(
        number=slot,
        fields=row_fields(slot),
        champion=champion_row(champion),
        sets=(picks + [SetPickView(None, None)] * SETS_PER_ROW)[:SETS_PER_ROW],
        minimums=[
            minimum_view(account, slot, champion, row, stat, ask, target) for stat in ROW_MINIMUMS
        ],
        rank=row.rank.name if isinstance(row.rank, Stat) else row.rank,
        skills=[(goal_skill, name) for goal_skill, name, _ in skills],
        skill=row.skill if row.skill in {s for s, _, _ in skills} else default_skill(skills),
    )


def minimum_view(
    account: Account,
    slot: int,
    champion: Champion,
    row: RowAsk,
    stat: Stat,
    ask: GearAsk,
    target: EnemyCard,
) -> MinimumView:
    value = minimum_value(account, champion, row, stat, ask, target)
    note = None

    if stat == Stat.ACC and value is not None:
        note = f"{percent(resist_chance(value, target.resistance))} resisted"
    elif stat == Stat.RES and value is not None:
        note = f"resists {percent(resist_chance(target.accuracy, value))}"
    elif stat == Stat.CR and isinstance(row.minimums[stat], Default) and value:
        note = "for damage"

    shown = "" if value is None else f"{value * 100 if stat == Stat.CR else value:g}"
    placeholder = str(resistance_for_cap(target.accuracy)) if stat == Stat.RES else ""
    return MinimumView(minimum_field(stat, slot), STAT_LABELS[stat], shown, note, placeholder)


def minimum_value(
    account: Account, champion: Champion, row: RowAsk, stat: Stat, ask: GearAsk, target: EnemyCard
) -> float | None:
    """The minimum as typed, else its default; ACC still at the old target's default follows
    the new one's. ACC's default is what resists as little as can be (`accuracy_for_floor`)."""
    asked: Minimum = row.minimums[stat]
    old = accuracy_for_floor(ask.defaults_res) if ask.defaults_res is not None else None

    match stat, asked:
        case Stat.ACC, Default():
            debuffer = places_debuffs(account, champion)
            return float(accuracy_for_floor(target.resistance)) if debuffer else None

        case Stat.ACC, float() if asked == old:
            return float(accuracy_for_floor(target.resistance))

        case Stat.CR, Default():
            return 1.0 if row.rank == DAMAGE else None

        case _, Default():
            return None

        case _:
            return asked


def places_debuffs(account: Account, champion: Champion) -> bool:
    return any(tag.side == Side.DEBUFF for tag in kit_of(account, champion).tags)


def damage_skills(
    account: Account, champion: Champion, defence: float
) -> list[tuple[int, str, DamageGoal]]:
    """The champion's skills whose damage can be ranked, against `defence`."""
    found = []

    for skill_id in champion.skills_in(account.tables):
        skill = account.tables.skills.get(skill_id)
        if skill is None:
            continue

        match damage_goal(skill, champion, defence):
            case Unsupported():
                continue
            case goal:
                found.append((skill_id, skill.name, goal))

    return found


def default_skill(skills: list[tuple[int, str, DamageGoal]]) -> int | None:
    """The last skill that can be ranked: usually the champion's big hit."""
    return skills[-1][0] if skills else None


def row_goal(
    account: Account, champion: Champion, asked: RowAsk, row: RowView, target: EnemyCard
) -> Goal:
    """What the row ranks: a stat, a skill's damage against the target's DEF, or a rate
    against its RES or ACC (SPD when nothing it names can be)."""
    match asked.rank:
        case Stat() as stat:
            return stat

        case "LANDS":
            return Lands(target.resistance)

        case "RESISTS":
            return Resists(target.accuracy)

        case _ if row.skill is not None:
            skills = {s: g for s, _, g in damage_skills(account, champion, target.defence)}
            return skills.get(row.skill, Stat.SPD)

        case _:
            return Stat.SPD


def member_request(
    account: Account,
    champion: Champion,
    asked: RowAsk,
    ask: GearAsk,
    target: EnemyCard,
    goal: Goal,
) -> Request:
    minimums = {
        stat: value
        for stat in ROW_MINIMUMS
        if (value := minimum_value(account, champion, asked, stat, ask, target)) is not None
    }
    return Request(
        champion=champion,
        minimums=minimums,
        maximums={},
        set_minimums=asked.sets,
        ranking=(goal,),
        slack=SLACK,
        builds=1,
        gear=ask.gear,
        above_level=DEFAULT_ABOVE_LEVEL,
    )


def solve_team(
    account: Account,
    ask: GearAsk,
    champions: list[Champion],
    rows: list[RowView],
    target: EnemyCard,
) -> TeamResult | TeamShortfall | Stopped:
    assumptions = read_assumptions(STORE, account)
    members = []
    requests = []

    for champion, row in zip(champions, rows, strict=True):
        asked = ask.rows[row.number - 1]
        goal = row_goal(account, champion, asked, row, target)
        request = member_request(account, champion, asked, ask, target, goal)
        assumed, request = assume(account, request, assumptions)
        members.append(Member(assumed, request))
        requests.append(request)

    started = time.monotonic()
    outcome = find_team_builds(members)
    seconds = time.monotonic() - started
    reserved = reservations(account, ask.gear.rules)

    match outcome:
        case Stopped():
            return outcome

        case Clash():
            return TeamShortfall(clash=True, members=[])

        case Unmet(members=why):
            return TeamShortfall(
                clash=False,
                members=[
                    (champion_row(r.champion), shortfall_lines(reason, r))
                    for r, reason in zip(requests, why, strict=True)
                    if reason is not None
                ],
            )

        case team:
            return TeamResult(
                [
                    member_result(account, request, build, reserved, target)
                    for request, build in zip(requests, team, strict=True)
                ],
                seconds,
                filter_form(ask.gear),
                [champion.id for champion in champions],
            )


def member_result(
    account: Account, request: Request, build: Build, reserved: Reservations, target: EnemyCard
) -> MemberResult:
    champion = request.champion
    sets = account.tables.sets
    worn = worn_gear(account, champion)
    current = build_stats(champion, worn, account.tables)
    goal = request.damage_goal()
    now_damage = estimate_damage(goal, current, worn, sets) if goal else None
    extra = (
        [damage_cell(estimate_damage(goal, build.stats, build.artifacts, sets), now_damage)]
        if goal
        else []
    )
    now_extra = [damage_cell(now_damage, None)] if goal and now_damage is not None else []
    return MemberResult(
        champion=champion_row(champion),
        current=stat_cells(current, None) + now_extra,
        build=build_view(1, build, current, account, champion, extra, reserved),
        damage=f"{goal.skill_name} crit vs {goal.enemy_defence:g} DEF" if goal else None,
        resisted=percent(resist_chance(build.stats[Stat.ACC], target.resistance)),
        resists=percent(resist_chance(target.accuracy, build.stats[Stat.RES])),
    )


def percent(chance: float) -> str:
    return f"{chance:.1%}"


def shortfall_lines(reason: SetsRuleOut | Shortfall, request: Request) -> list[str]:
    match reason:
        case SetsRuleOut(reason=text):
            return [text]

        case Shortfall(highest=highest, lowest=lowest):
            return [
                f"{STAT_LABELS[stat]} at least {format_stat(stat, request.minimums[stat])}: "
                f"best possible {format_stat(stat, best)}"
                for stat, best in highest.items()
            ] + [
                f"{STAT_LABELS[stat]} at most {format_stat(stat, request.maximums[stat])}: "
                f"lowest possible {format_stat(stat, low)}"
                for stat, low in lowest.items()
            ]
