"""
chimera.py - the Chimera trials page: the rotation (the column holding its mythical
materials), the team's five slots (champions the user puts there), the teams the search
finds around them (every way to clear all the trials, listed a few at a time), and the
column's nine trials (Ram, Lion and Snake; Easy, Normal and Hard), each highlighted when the
team shown can clear it in one Ultra Nightmare fight.

- `DEFAULT_COLUMN`, `GRADES`, `FIRST_SHOWN`, `MORE`, `MAX_LISTED`: what the page opens on
  and offers
- `ChoiceView`, `SlotView`, `NeedView`, `TrialView`, `FormRow`, `OptionView`, `ChimeraPage`:
  the views
- `chimera_page`: what the page asks for
- `slot_view`, `option_view`, `form_rows`, `trial_view`, `choice_label`:
  its pieces
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.chimera import (
    ANIMAL_FORMS,
    LEVELS,
    PARTS,
    TOXIC_SET,
    Lineup,
    Member,
    TrialCover,
    check_lineup,
    fill_lineup,
)
from optimiser.enemies import Enemies
from webui.forms import SlotPick, Unmatched
from webui.service.views import ChampionRow, champion_row

DEFAULT_COLUMN = "Tail"  # where the game's data puts Ultra Nightmare's mythical materials
GRADES = (6, 5, 4)
FIRST_SHOWN = 3  # teams a run shows at first
MORE = 9  # teams each "show more" adds
MAX_LISTED = 300  # most a page lists


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
class NeedView:
    """A need: who on the team brings it, and `notes` (gear that does, or for a count, the
    effects the team brings)."""

    label: str
    met: bool
    champions: list[ChampionRow]
    notes: list[str]


@dataclass(frozen=True)
class TrialView:
    """A trial; `contributors`: every champion bringing one of its needs, once; `waits_on`:
    the level that must be cleared first, when the team meets this one's needs but not that's."""

    level: str
    description: str
    target: str  # "2,000,000", "7"
    damage: bool  # the target is damage (else a count)
    met: bool
    needs: list[NeedView]
    contributors: list[ChampionRow]
    waits_on: str | None = None


@dataclass(frozen=True)
class FormRow:
    form: str
    trials: list[TrialView]  # Easy, Normal, Hard
    cleared: int


@dataclass(frozen=True)
class OptionView:
    """A team the search found: its slots (the user's champions and the suggested ones), the
    trials it clears, and each form's trials as met or not (Easy first), for a glance."""

    number: int  # 1 first
    slots: list[SlotView]
    cleared: int
    glance: list[tuple[str, list[bool]]]  # form -> met, by level


@dataclass(frozen=True)
class ChimeraPage:
    column: str
    columns: tuple[str, ...]
    min_grade: int
    grades: tuple[int, ...]
    toxic: bool  # any champion may wear a Toxic set (Poison)
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
    rows: list[FormRow]
    problems: list[str]  # where the trial needs disagree with the game's data


def chimera_page(
    account: Account,
    enemies: Enemies,
    column: str,
    min_grade: int,
    picks: tuple[SlotPick, ...],
    run: bool,
    option: int,
    listed: int,
    toxic: bool,
) -> ChimeraPage:
    """`column` must be one of `PARTS`. With `run`, the search fills the open slots (and those
    whose text isn't a champion) every way it can, the page lists the first `listed` teams,
    and the trials show option number `option` (the first if there's no such option)."""
    slots = tuple(pick if isinstance(pick, Champion) else None for pick in picks)
    gear = (TOXIC_SET,) if toxic else ()

    if run:
        plan = fill_lineup(account, enemies, column, slots, min_grade, gear, listed)
    else:
        plan = check_lineup(account, enemies, column, slots, gear)

    shown = option if 1 <= option <= len(plan.options) else (1 if plan.options else None)
    lineup = plan.options[shown - 1] if shown else plan.lineup

    champions = sorted(account.champions.values(), key=lambda c: (c.name, -c.grade, -c.level))
    return ChimeraPage(
        column=column,
        columns=PARTS,
        min_grade=min_grade,
        grades=GRADES,
        toxic=toxic,
        slots=[
            slot_view(member, pick) for member, pick in zip(plan.lineup.slots, picks, strict=True)
        ],
        choices=[ChoiceView(choice_label(c)) for c in champions],
        ran=run,
        candidates=plan.candidates,
        options=[option_view(number, team) for number, team in enumerate(plan.options, 1)],
        found=plan.found,
        complete=plan.complete,
        partial=plan.partial,
        listed=len(plan.options),
        more=min(listed + MORE, plan.found) if plan.found > listed else 0,
        shown=shown,
        cleared=lineup.cleared,
        rows=form_rows(lineup),
        problems=list(plan.problems),
    )


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
        glance=[(row.form, [trial.met for trial in row.trials]) for row in rows],
    )


def form_rows(lineup: Lineup) -> list[FormRow]:
    by_form = {form: [c for c in lineup.trials if c.trial.form == form] for form in ANIMAL_FORMS}
    return [
        FormRow(
            form,
            [trial_view(c) for c in sorted(covers, key=level_order)],
            sum(c.met for c in covers),
        )
        for form, covers in by_form.items()
    ]


def level_order(cover: TrialCover) -> int:
    return LEVELS.index(cover.trial.level)


def trial_view(cover: TrialCover) -> TrialView:
    contributors = {c.id: c for need in cover.needs for c in need.by}
    return TrialView(
        level=cover.trial.level,
        description=cover.trial.description,
        target=f"{cover.trial.target:,.0f}",
        damage=cover.trial.damage,
        met=cover.met,
        needs=[
            NeedView(n.label, n.met, [champion_row(c) for c in n.by], list(n.notes))
            for n in cover.needs
        ],
        contributors=[champion_row(c) for c in contributors.values()],
        waits_on=waits_on(cover),
    )


def waits_on(cover: TrialCover) -> str | None:
    if cover.met or not all(need.met for need in cover.needs):
        return None

    return LEVELS[LEVELS.index(cover.trial.level) - 1]


def choice_label(champion: Champion) -> str:
    return f"{champion.name}, {champion.grade}★ L{champion.level} #{champion.id}"
