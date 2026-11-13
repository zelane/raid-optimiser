"""
chimera.py - the Chimera trials page: the rotation (the column holding its mythical
materials), the team's five slots (champions the user puts there), the teams the search
finds around them (every way to clear all the trials, listed a few at a time), and the
column's nine trials (Ram, Lion and Snake; Easy, Normal and Hard), each highlighted when the
team shown can clear it in one Ultra Nightmare fight.

- `MORE`: how many more teams "show more" lists
- `ColumnView`, `ChoiceView`, `SlotView`, `IconView`, `Contributor`, `NeedView`, `TrialView`,
  `FormRow`, `OptionView`, `WantView`, `WantGroup`, `GearView`, `GearGroup`, `AssumedView`,
  `ChimeraPage`: the views
- `chimera_page`: what the page asks for
- `rotation_column`: the column the game's current raid puts the mythical materials in
- `column_views`, `easy_ram_trials`, `trial_terms`, `slot_view`, `option_view`, `form_rows`,
  `trial_view`, `need_view`, `waits_on`, `WANT_GROUPS`, `want_groups`, `want_view`,
  `gear_groups`, `gear_view`, `assumed_views`, `assumed_view`, `choice_label`, `percent`: its
  pieces
- `ICON_NAMES`, `icon_view`, `icon_url`, `icon_name`: the game's icons for buffs, debuffs and
  effects
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from optimiser.account import Account, Champion
from optimiser.chimera.cover import Lineup, Member, NeedCover, TrialCover
from optimiser.chimera.gear import Assumed, Gear, Loadout
from optimiser.chimera.plan import Brief, check_lineup, fill_lineup
from optimiser.chimera.rotation import mythical_column
from optimiser.chimera.tags import Side, Tag, only_in, plain_label
from optimiser.chimera.trials import ANIMAL_FORMS, LEVELS, PARTS, PLAN_DIFFICULTY
from optimiser.enemies import Enemies, Trial
from webui.forms import (
    FIRST_SHOWN,
    GRADES,
    ChimeraRequest,
    Fill,
    Offers,
    SlotPick,
    Unmatched,
)
from webui.service.views import ChampionRow, asset_url, champion_row

MORE = 9  # teams each "show more" adds


@dataclass(frozen=True)
class ColumnView:
    """A trial column: the game doesn't name them, so `hint` names its Easy Ram trial's
    statuses; `mythical`: the game's current raid puts the mythical materials in it."""

    part: str
    hint: str
    mythical: bool


@dataclass(frozen=True)
class ChoiceView:
    """A champion as the slot picker lists it: "Name, 6★ L60 #id" (the form reads the id)."""

    label: str


@dataclass(frozen=True)
class SlotView:
    """A team slot: its champion (None when open), as the picker shows it, and whether the
    search suggested it (else the user chose it) and the team needs it. `problem`: why the
    text typed in it isn't a champion (the slot stays open, the text kept)."""

    champion: ChampionRow | None
    choice: str  # the picker's text; "" when open
    suggested: bool
    needed: bool
    problem: str | None = None


@dataclass(frozen=True)
class IconView:
    """A buff, debuff or effect as an icon: the game's art, or None (the page draws a glyph)."""

    label: str
    url: str | None


@dataclass(frozen=True)
class Contributor:
    """A champion bringing a need, and how far its best source can be counted on."""

    champion: ChampionRow
    score: int  # %
    detail: str  # "2 turns, every 3 turns, 75% chance"


@dataclass(frozen=True)
class NeedView:
    """A need: who on the team brings it, `asks` (what would do), `brought` (for a count, the
    effects the team brings), `notes` (gear that meets it) and its `score` (%)."""

    label: str
    met: bool
    contributors: list[Contributor]
    notes: list[str]
    asks: list[IconView]
    brought: list[IconView]
    score: int


@dataclass(frozen=True)
class TrialView:
    """A trial; `waits_on`: the level that must be cleared first, when the team meets this
    one's needs but not that's."""

    level: str
    description: str
    target: str  # "2,000,000", "7"
    damage: bool  # the target is damage (else a count)
    met: bool
    needs: list[NeedView]
    waits_on: str | None = None


@dataclass(frozen=True)
class FormRow:
    form: str
    trials: list[TrialView]  # Easy, Normal, Hard
    cleared: int
    icon_url: str | None  # the game's trial art for the form


@dataclass(frozen=True)
class OptionView:
    """A team the search found: its slots (the user's champions and the suggested ones), the
    trials it clears, and each form's trials as met or not (Easy first), for a glance."""

    number: int  # 1 first
    slots: list[SlotView]
    cleared: int
    score: int  # % (`chimera.team_score`)
    glance: list[tuple[str, list[bool]]]  # form -> met, by level


@dataclass(frozen=True)
class WantView:
    """Something the user can ask every team to bring, and whether they have; `note`: where
    it only lands (Fear: the Ram form; `only_in`)."""

    key: str  # `Tag.key`
    label: str
    wanted: bool
    note: str | None
    icon_url: str | None


@dataclass(frozen=True)
class WantGroup:
    """The debuffs, the buffs or the effects on offer; `chosen`: how many are wanted."""

    title: str
    wants: list[WantView]
    chosen: int


@dataclass(frozen=True)
class GearView:
    """A set or relic the user can let any champion wear, what it brings, and whether they
    have; `faction`: only a champion of it gets the relic's skill."""

    key: str
    name: str
    faction: str | None
    on: bool
    brings: list[IconView]


@dataclass(frozen=True)
class GearGroup:
    title: str
    gear: list[GearView]
    chosen: int


@dataclass(frozen=True)
class AssumedView:
    """Something assumed: for the team (`champion` None) or one champion. `key` is how the
    page's URL names it."""

    key: str
    label: str
    champion: str | None
    icon: IconView


@dataclass(frozen=True)
class ChimeraPage:
    column: str
    columns: list[ColumnView]
    min_grade: int
    grades: tuple[int, ...]
    gear: list[GearGroup]  # sets, relics
    gear_on: list[GearView]  # the allowed ones
    assumed: list[AssumedView]
    wants: list[WantGroup]  # debuffs, buffs, effects
    wanted: list[WantView]  # the chosen ones, in that order
    extras: list[NeedView]  # who in the team shown brings the wanted debuffs
    slots: list[SlotView]
    choices: list[ChoiceView]  # every champion, by name
    ran: bool  # the search filled the open slots
    candidates: int  # champions it could add
    options: list[OptionView]  # best first, the first `listed` of `found`
    found: int  # teams the search found
    complete: bool  # no more exist than `found`
    partial: bool  # none clears every trial: these clear the most
    listed: int  # how many the page lists
    more: int  # how many the page lists after "show more" (0: no more to show)
    shown: int | None  # the option the trials show (its number); None: the slots as they are
    cleared: int  # by what the trials show
    score: int  # % of what the trials show (`chimera.team_score`)
    rows: list[FormRow]
    problems: list[str]  # where the trial needs disagree with the game's data


def chimera_page(
    account: Account, enemies: Enemies, request: ChimeraRequest, offers: Offers
) -> ChimeraPage:
    """With `request.fill`, the search fills the open slots (and those whose text isn't a
    champion) every way it can; else the slots are shown as they are."""
    picks, wanted, loadout = request.picks, request.wanted, request.loadout
    brief = Brief(request.column, wanted, loadout)
    slots = tuple(pick if isinstance(pick, Champion) else None for pick in picks)

    match request.fill:
        case None:
            plan = check_lineup(account, enemies, brief, slots)
            listed, option = FIRST_SHOWN, 1
        case Fill(listed=listed, option=option):
            plan = fill_lineup(account, enemies, brief, slots, request.min_grade, listed)

    shown = option if 1 <= option <= len(plan.options) else (1 if plan.options else None)
    lineup = plan.options[shown - 1] if shown else plan.lineup
    allowed = {g.key for g in loadout.gear}

    champions = sorted(account.champions.values(), key=lambda c: (c.name, -c.grade, -c.level))
    return ChimeraPage(
        column=request.column,
        columns=column_views(enemies, rotation_column(account, enemies, datetime.now(UTC))),
        min_grade=request.min_grade,
        grades=GRADES,
        gear=gear_groups(offers.gear, allowed),
        gear_on=[gear_view(g, True) for g in offers.gear if g.key in allowed],
        assumed=assumed_views(loadout),
        wants=want_groups(offers.tags, wanted),
        wanted=[want_view(tag, True) for tag in wanted],
        extras=[need_view(need) for need in lineup.extras],
        slots=[
            slot_view(member, pick) for member, pick in zip(plan.lineup.slots, picks, strict=True)
        ],
        choices=[ChoiceView(choice_label(c)) for c in champions],
        ran=request.fill is not None,
        candidates=plan.candidates,
        options=[option_view(number, team) for number, team in enumerate(plan.options, 1)],
        found=plan.found,
        complete=plan.complete,
        partial=plan.partial,
        listed=len(plan.options),
        more=min(listed + MORE, plan.found) if plan.found > listed else 0,
        shown=shown,
        cleared=lineup.cleared,
        score=percent(lineup.score),
        rows=form_rows(lineup),
        problems=list(plan.problems),
    )


def rotation_column(account: Account, enemies: Enemies, now: datetime) -> str | None:
    """None when the snapshot has no raid (the game hadn't loaded the Chimera)."""
    raid = account.chimera_raid
    return mythical_column(enemies.chimera, raid, now) if raid else None


def column_views(enemies: Enemies, mythical: str | None) -> list[ColumnView]:
    easy_ram = {t.part: t for t in easy_ram_trials(enemies)}
    return [ColumnView(part, trial_terms(easy_ram[part]), part == mythical) for part in PARTS]


def easy_ram_trials(enemies: Enemies) -> list[Trial]:
    """The trial each column starts with, as the game lists them."""
    tier = next(t for t in enemies.chimera.tiers if t.difficulty == PLAN_DIFFICULTY)
    return [t for t in tier.trials if (t.form, t.level) == (ANIMAL_FORMS[0], LEVELS[0])]


def trial_terms(trial: Trial) -> str:
    """The statuses a trial's text names ("[Decrease DEF]", …), in order, once each."""
    return " + ".join(dict.fromkeys(re.findall(r"\[([^\]]+)\]", trial.description)))


def slot_view(member: Member | None, pick: SlotPick) -> SlotView:
    if member is None and isinstance(pick, Unmatched):
        return SlotView(None, pick.text, suggested=False, needed=False, problem=pick.reason)

    if member is None:
        return SlotView(None, "", suggested=False, needed=False)

    return SlotView(
        champion_row(member.champion),
        choice_label(member.champion),
        suggested=not member.chosen,
        needed=member.needed,
    )


def option_view(number: int, team: Lineup) -> OptionView:
    rows = form_rows(team)
    return OptionView(
        number=number,
        slots=[slot_view(member, None) for member in team.slots],
        cleared=team.cleared,
        score=percent(team.score),
        glance=[(row.form, [trial.met for trial in row.trials]) for row in rows],
    )


def form_rows(lineup: Lineup) -> list[FormRow]:
    by_form = {form: [c for c in lineup.trials if c.trial.form == form] for form in ANIMAL_FORMS}
    return [
        FormRow(
            form,
            [trial_view(c) for c in sorted(covers, key=level_order)],
            sum(c.met for c in covers),
            asset_url("chimera", f"{form}_Hard"),
        )
        for form, covers in by_form.items()
    ]


def level_order(cover: TrialCover) -> int:
    return LEVELS.index(cover.trial.level)


def trial_view(cover: TrialCover) -> TrialView:
    return TrialView(
        level=cover.trial.level,
        description=cover.trial.description,
        target=f"{cover.trial.target:,.0f}",
        damage=cover.trial.damage,
        met=cover.met,
        needs=[need_view(n) for n in cover.needs],
        waits_on=waits_on(cover),
    )


def gear_groups(offered: list[Gear], allowed: set[str]) -> list[GearGroup]:
    groups = []

    for kind, title in (("set", "Artifact sets"), ("relic", "Relics you own")):
        views = [gear_view(g, g.key in allowed) for g in offered if g.kind == kind]
        groups.append(GearGroup(title, views, sum(v.on for v in views)))

    return groups


def gear_view(gear: Gear, on: bool) -> GearView:
    brings = [icon_view(tag) for tag in gear.tags if tag.side != Side.MECHANIC]
    return GearView(gear.key, gear.name, gear.faction, on, sorted(brings, key=lambda i: i.label))


def assumed_views(loadout: Loadout) -> list[AssumedView]:
    """The team's assumptions (assumed gear) and the single champions'."""
    team = [
        AssumedView(tag.key, plain_label(tag), None, icon_view(tag))
        for gear in loadout.gear
        if gear.kind == "assumed"
        for tag in gear.tags
    ]
    single = [assumed_view(a) for a in loadout.assumed]
    return team + single


def assumed_view(assumed: Assumed) -> AssumedView:
    tag = assumed.tag
    return AssumedView(assumed.key, plain_label(tag), assumed.champion.name, icon_view(tag))


WANT_GROUPS = (
    (Side.DEBUFF, "Debuffs on the Chimera"),
    (Side.BUFF, "Buffs"),
    (Side.EFFECT, "Effects"),
)


def want_groups(offered: list[Tag], wanted: tuple[Tag, ...]) -> list[WantGroup]:
    groups = []

    for side, title in WANT_GROUPS:
        tags = [tag for tag in offered if tag.side == side]
        views = [want_view(tag, tag in wanted) for tag in tags]
        groups.append(WantGroup(title, views, sum(view.wanted for view in views)))

    return groups


def want_view(tag: Tag, wanted: bool) -> WantView:
    forms = only_in(tag)
    note = f"{' or '.join(forms)} form only" if forms else None
    return WantView(tag.key, plain_label(tag), wanted, note, icon_url(tag))


# Status kinds whose icon (`statuses/`, the game's sprite names) is named otherwise; the rest
# follow `icon_name`'s rules.
ICON_NAMES = {
    "Burn": "AoEContinuousDamage",
    "SimpleStoneSkin": "StoneSkin",
    "ReflectiveStoneSkin": "StoneSkin",
    "Counterattack": "StatusCounterattack",
    "LesserSeal": "Seal",
    "GreaterSeal": "Seal2",
    "NecrosisSource": "Necrosis",
    "DuelTargetMark": "Duel",
    "ArtifactSet_Shield": "Shield",
    # Skill effects with a status of the same sense.
    "IncreaseStamina": "IncreaseStamina",
    "Revive": "ReviveOnDeath",
    "Heal": "ContinuousHeal",
    "PassiveBlockDebuff": "BlockDebuff",
    "PassiveCounterattack": "StatusCounterattack",
    "PassiveReflectDamage": "ReflectDamage",
    "PassiveUnkillable": "Unkillable",
}
STAT_STATUSES = ("Attack", "Defence", "Speed", "Accuracy", "Resistance", "CriticalChance")
STAT_STATUSES += ("CriticalDamage",)


def icon_url(tag: Tag) -> str | None:
    """The game's icon for a buff, debuff or effect, if it has one."""
    return asset_url("statuses", icon_name(tag))


def icon_name(tag: Tag) -> str:
    """Stat buffs and debuffs are "StatusIncrease…" / "StatusReduce…"."""
    if name := ICON_NAMES.get(tag.name):
        return name

    for prefix, sprite in (("Increase", "StatusIncrease"), ("Decrease", "StatusReduce")):
        stat = tag.name.removeprefix(prefix)
        if tag.name.startswith(prefix) and stat in STAT_STATUSES:
            return sprite + stat

    return tag.name


def need_view(need: NeedCover) -> NeedView:
    contributors = [
        Contributor(champion_row(champion), percent(rating.score), rating.detail)
        for champion, rating in zip(need.by, need.ratings, strict=True)
    ]
    return NeedView(
        label=need.label,
        met=need.met,
        contributors=sorted(contributors, key=lambda c: -c.score),
        notes=list(need.notes),
        score=percent(need.score),
        asks=[icon_view(tag) for tag in need.asks],
        brought=[icon_view(tag) for tag in need.brought],
    )


def percent(score: float) -> int:
    return round(score * 100)


def icon_view(tag: Tag) -> IconView:
    return IconView(plain_label(tag), icon_url(tag))


def waits_on(cover: TrialCover) -> str | None:
    if cover.met or not all(need.met for need in cover.needs):
        return None

    return LEVELS[LEVELS.index(cover.trial.level) - 1]


def choice_label(champion: Champion) -> str:
    return f"{champion.name}, {champion.grade}★ L{champion.level} #{champion.id}"
