"""
chimera.py - the Chimera trials page: the rotation (the column holding its mythical
materials), the team's five slots (champions the user puts there), the teams the search
finds around them (every way to clear all the trials, listed a few at a time), and the
column's nine trials (Ram, Lion and Snake; Easy, Normal and Hard), each highlighted when the
team shown can clear it in one Ultra Nightmare fight.

The team's panels (slots, what to bring, gear) and each need's view are `service.team`'s.

- `MORE`: how many more teams "show more" lists
- `ColumnView`, `TrialView`, `FormRow`, `OptionView`, `ChimeraPage`: the views
- `chimera_page`: what the page asks for
- `rotation_column`: the column the game's current raid puts the mythical materials in
- `column_views`, `easy_ram_trials`, `trial_terms`, `form_note`, `option_view`, `form_rows`,
  `level_order`, `trial_view`, `waits_on`: its pieces
"""

import re
from dataclasses import dataclass
from datetime import datetime

from optimiser.account import Account, Champion
from optimiser.chimera.plan import Brief, check_lineup, fill_lineup
from optimiser.chimera.rotation import mythical_column
from optimiser.chimera.tags import CHIMERA, only_in
from optimiser.chimera.trials import ANIMAL_FORMS, LEVELS, PARTS, PLAN_DIFFICULTY
from optimiser.enemies import Enemies, Trial
from optimiser.teams.cover import Lineup, ObjectiveCover
from optimiser.teams.tags import Tag
from webui.forms.chimera import ChimeraRequest
from webui.forms.team import FIRST_SHOWN, GRADES, Fill, Offers
from webui.service.team import (
    NeedView,
    PageUrl,
    SlotView,
    TeamLinks,
    TeamView,
    listing,
    need_view,
    percent,
    slot_view,
    slot_worn,
    team_view,
)
from webui.service.views import asset_url

MORE = 9  # teams each "show more" adds


@dataclass(frozen=True)
class ColumnView:
    """A trial column: the game doesn't name them, so `hint` names its Easy Ram trial's
    statuses; `mythical`: the game's current raid puts the mythical materials in it."""

    part: str
    hint: str
    mythical: bool


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
    show_url: str  # the page showing its trials
    use_url: str  # the page with it in the slots


@dataclass(frozen=True)
class ChimeraPage:
    column: str
    columns: list[ColumnView]
    min_grade: int
    grades: tuple[int, ...]
    team: TeamView  # the slots, what to bring, gear
    extras: list[NeedView]  # who in the team shown brings the wanted debuffs
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
    links: TeamLinks


def chimera_page(
    account: Account,
    enemies: Enemies,
    request: ChimeraRequest,
    offers: Offers,
    rotation: str | None,
) -> ChimeraPage:
    """With `request.fill`, the search fills the open slots (and those whose text isn't a
    champion) every way it can; else the slots are shown as they are. `rotation`: the column
    the current raid puts the mythical materials in (`rotation_column`), if known."""
    ask = request.team
    slots = tuple(pick if isinstance(pick, Champion) else None for pick in ask.picks)
    worn = slot_worn(account, ask, offers, slots)
    brief = Brief(request.column, ask.wanted, ask.loadout, ask.counts, worn)

    match request.fill:
        case None:
            plan = check_lineup(account, enemies, brief, slots)
            listed, option = FIRST_SHOWN, 1
        case Fill(listed=listed, option=option):
            plan = fill_lineup(account, enemies, brief, slots, request.min_grade, listed)

    shown = option if 1 <= option <= len(plan.options) else (1 if plan.options else None)
    lineup = plan.options[shown - 1] if shown else plan.lineup
    team = team_view(account, plan.lineup.slots, ask, offers, CHIMERA, form_note)
    base = (("column", request.column), ("min_grade", str(request.min_grade)))
    url = PageUrl("/chimera", base, team)
    shown_listed = len(plan.options)
    more = min(listed + MORE, plan.found) if plan.found > listed else 0

    return ChimeraPage(
        column=request.column,
        columns=column_views(enemies, rotation),
        min_grade=request.min_grade,
        grades=GRADES,
        team=team,
        extras=[need_view(need) for need in lineup.extras],
        ran=request.fill is not None,
        candidates=plan.candidates,
        options=[
            option_view(number, option_team, plan.trials, url, shown_listed)
            for number, option_team in enumerate(plan.options, 1)
        ],
        found=plan.found,
        complete=plan.complete,
        partial=plan.partial,
        listed=shown_listed,
        more=more,
        shown=shown,
        cleared=lineup.cleared,
        score=percent(lineup.score),
        rows=form_rows(lineup, plan.trials),
        problems=list(plan.problems),
        links=url.links(request.fill is not None, listing(more, shown or 1) if more else None),
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


def form_note(tag: Tag) -> str | None:
    """Where a debuff the Chimera is otherwise immune to lands: "Ram form only"."""
    forms = only_in(tag)
    return f"{' or '.join(forms)} form only" if forms else None


def option_view(
    number: int, team: Lineup, trials: dict[int, Trial], url: PageUrl, listed: int
) -> OptionView:
    """`url`: the page's, `listed` the options it lists (kept when it shows this one)."""
    rows = form_rows(team, trials)
    slots = [slot_view(member, None) for member in team.slots]
    return OptionView(
        number=number,
        slots=slots,
        cleared=team.cleared,
        score=percent(team.score),
        glance=[(row.form, [trial.met for trial in row.trials]) for row in rows],
        show_url=url.to(url.team.slots, listing(listed, number)),
        use_url=url.to(slots),
    )


def form_rows(lineup: Lineup, trials: dict[int, Trial]) -> list[FormRow]:
    """Each form's trials (the lineup's objectives are keyed by their skill), Easy first."""
    covered = [(c, trials[c.objective.key]) for c in lineup.objectives]
    by_form = {form: [(c, t) for c, t in covered if t.form == form] for form in ANIMAL_FORMS}
    return [
        FormRow(
            form,
            [trial_view(c, t) for c, t in sorted(pairs, key=lambda pair: level_order(pair[1]))],
            sum(c.met for c, _ in pairs),
            asset_url("chimera", f"{form}_Hard"),
        )
        for form, pairs in by_form.items()
    ]


def level_order(trial: Trial) -> int:
    return LEVELS.index(trial.level)


def trial_view(cover: ObjectiveCover, trial: Trial) -> TrialView:
    return TrialView(
        level=trial.level,
        description=trial.description,
        target=f"{trial.target:,.0f}",
        damage=trial.damage,
        met=cover.met,
        needs=[need_view(n) for n in cover.needs],
        waits_on=waits_on(cover, trial),
    )


def waits_on(cover: ObjectiveCover, trial: Trial) -> str | None:
    if cover.met or not all(need.met for need in cover.needs):
        return None

    return LEVELS[LEVELS.index(trial.level) - 1]
