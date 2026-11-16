"""
teams.py - the team finder page: what the team is for (anything, or a stage from the target
picker: a Faction Wars stage's challenge, the Chimera's column of trials, and any stage's hold
on who may enter), what every team must bring besides (tags, so many different debuffs or
buffs) and the gear it may count on, the team's slots, the teams the search finds (every way
to bring it all, listed a few at a time) and, for the team shown, who brings what (the
Chimera's on its trial board, `service.chimera`).

- `MORE`, `DEFAULT_COLUMN`: how many more teams "show more" lists; the Chimera's column when
  the game's raid doesn't say
- `FactionWars`, `ChimeraTrials`, `Content`: what a stage asks
- `ChallengeView`, `AgainstView`, `OptionView`, `TeamsPage`: the views
- `content`, `never_lands`: the stage resolved, first (what it is decides the page's offers)
- `teams_page`: what the page asks for
- `stage_url`: the page for a stage (the Info page links its stages)
- `gear_url`: Team gear for a team found, against the stage's enemy picked
- `stage_goals`, `finder_goals`, `against_view`, `page_query`, `option_view`: its pieces
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from optimiser.account import Account, Champion
from optimiser.chimera.plan import Brief, column_goals
from optimiser.chimera.tags import CHIMERA, NEVER_LANDS
from optimiser.chimera.trials import stage_tier
from optimiser.enemies import FACTION_WARS, Enemies, Restriction, Rotating, Trial, team_restriction
from optimiser.factionwars import ENEMIES, Challenge, challenge
from optimiser.teams.cover import Lineup
from optimiser.teams.find import check_slots, find_teams
from optimiser.teams.gear import Gear, with_gear
from optimiser.teams.kits import candidates
from optimiser.teams.needs import AnyOf, Distinct, Goals, Objective
from optimiser.teams.tags import Tag
from webui.forms.targets import saved_query
from webui.forms.team import GRADES, Fill, Offers, TeamAsk
from webui.forms.team_gear import PAGE_FIELDS
from webui.forms.teams import TEAM_SIZE, Against, TeamsRequest
from webui.service.chimera import (
    ChimeraView,
    FormRow,
    chimera_view,
    form_note,
    form_rows,
    glance,
)
from webui.service.finder import OnlyView, only_view, restriction_label
from webui.service.targets import TargetPicker, target_picker
from webui.service.team import (
    NeedView,
    PageUrl,
    Query,
    SlotView,
    TeamLinks,
    TeamView,
    listing,
    need_view,
    no_note,
    percent,
    slot_view,
    slot_worn,
    team_view,
    trimmed,
)
from webui.service.views import asset_url

MORE = 9  # teams each "show more" adds
DEFAULT_COLUMN = "Tail"  # where the mythical materials are at prize offset 0


@dataclass(frozen=True)
class FactionWars:
    """A Faction Wars stage: its challenge, if it has one."""

    challenge: Challenge | None


@dataclass(frozen=True)
class ChimeraTrials:
    """A Chimera stage: its tier, the column of trials asked, and the column this raid's
    mythical materials are in (None: the snapshot doesn't say)."""

    difficulty: str
    column: str
    rotation: str | None


@dataclass(frozen=True)
class Content:
    """The stage picked (`picker`), who it admits, and what it asks besides (None: nothing)."""

    picker: TargetPicker
    restriction: Restriction | Rotating | None
    asks: FactionWars | ChimeraTrials | None


@dataclass(frozen=True)
class ChallengeView:
    """A Faction Wars stage's challenge: its text (None: it has none), `checked`: the finder
    reads it (else nothing is asked of the team for it)."""

    text: str | None
    checked: bool


@dataclass(frozen=True)
class AgainstView:
    """The stage picked: what it admits (only they're searched; `rotating`: it changes with
    the account, unknown which), a crypt's banner, the slots' champions it refuses, the
    champion finder's hold, and what it asks: a challenge or the Chimera's column."""

    picker: TargetPicker
    admits: str | None
    rotating: bool
    faction_url: str | None
    refused: list[str]
    only: OnlyView | None
    challenge: ChallengeView | None
    chimera: ChimeraView | None


@dataclass(frozen=True)
class OptionView:
    """A team the search found: its slots, how many needs (or trials) it meets, its score (%),
    and for the Chimera each form's trials met or not (Easy first), for a glance."""

    number: int  # 1 first
    slots: list[SlotView]
    met: int
    score: int
    glance: list[tuple[str, list[bool]]]
    show_url: str  # the page showing its needs
    use_url: str  # the page with it in the slots
    gear_url: str  # Team gear for it


@dataclass(frozen=True)
class TeamsPage:
    against: AgainstView | None  # None: no stage, only what's asked besides
    min_grade: int
    grades: tuple[int, ...]
    team: TeamView
    ran: bool  # the search filled the open slots
    asked: bool  # something is needed (else there's nothing to search for)
    candidates: int  # champions it could add
    options: list[OptionView]
    found: int
    complete: bool
    partial: bool
    listed: int
    more: int  # how many the page lists after "show more" (0: no more to show)
    shown: int | None  # the option the needs show; None: the slots as they are
    unit: str  # what `met` counts: "needs", or the Chimera's "trials"
    met: int  # by the team shown
    needs: int  # in all
    score: int  # % of what's shown
    base_needs: list[NeedView]  # the challenge's, for the team shown
    rows: list[FormRow]  # the Chimera's trials, for the team shown
    extras: list[NeedView]  # what's asked besides, for the team shown
    links: TeamLinks


def content(enemies: Enemies, against: Against | None, rotation: str | None) -> Content | None:
    """The stage asked for (None: none); `rotation`: the column the game's current raid puts
    the Chimera's mythical materials in (`service.chimera.rotation_column`), if known."""
    if against is None:
        return None

    picker = target_picker(enemies, saved_query(against.target))
    stage = enemies.stages[picker.stage]
    asks: FactionWars | ChimeraTrials | None = None

    if tier := stage_tier(enemies, stage.id):
        column = against.column or rotation or DEFAULT_COLUMN
        asks = ChimeraTrials(tier.difficulty, column, rotation)
    elif stage.area == FACTION_WARS:
        asks = FactionWars(challenge(stage))

    return Content(picker, team_restriction(stage), asks)


def never_lands(base: Content | None) -> frozenset[str]:
    """The debuffs not worth offering: what the Chimera is immune to in every form."""
    return NEVER_LANDS if base and isinstance(base.asks, ChimeraTrials) else frozenset()


def teams_page(
    account: Account,
    enemies: Enemies,
    base: Content | None,
    request: TeamsRequest,
    offers: Offers,
) -> TeamsPage:
    """With `request.fill` (and something needed), the search fills the open slots every way
    it can, from the champions the stage admits; else the slots are shown as they are."""
    ask = request.team
    asks = base.asks if base else None
    restriction = base.restriction if base else None
    goals, trials, problems = stage_goals(enemies, asks, ask)
    asked = bool(goals.requirements)
    slots = tuple(pick if isinstance(pick, Champion) else None for pick in ask.picks)
    worn = slot_worn(account, ask, offers, slots)

    match request.fill:
        case Fill(listed=listed, option=option) if asked:
            pool = candidates(account, request.min_grade)

            if isinstance(restriction, Restriction):
                pool = [c for c in pool if restriction.admits(c)]

            found = find_teams(account, ask.loadout, slots, goals, pool, listed, worn)
            lineup, options = found.lineup, found.options
        case _:
            listed, option, found = 0, 1, None
            lineup, options = check_slots(account, ask.loadout, slots, goals, worn), ()

    shown = option if 1 <= option <= len(options) else (1 if options else None)
    team = options[shown - 1] if shown else lineup
    chimera = isinstance(asks, ChimeraTrials)
    base_needs = [] if chimera else [need_view(n) for c in team.objectives for n in c.needs]
    extras = [need_view(n) for n in team.extras]
    total = found.found if found else 0
    enemy, note = (CHIMERA, form_note) if chimera else (ENEMIES.name, no_note)
    team_shown = team_view(account, lineup.slots, ask, offers, enemy, note)
    url = PageUrl("/teams", page_query(base, request.min_grade), team_shown)
    more = min(listed + MORE, total) if total > listed else 0
    return TeamsPage(
        against=against_view(enemies, base, slots, problems) if base else None,
        min_grade=request.min_grade,
        grades=GRADES,
        team=team_shown,
        ran=request.fill is not None,
        asked=asked,
        candidates=found.candidates if found else 0,
        options=[
            option_view(number, o, trials, url, len(options), base)
            for number, o in enumerate(options, 1)
        ],
        found=total,
        complete=found.complete if found else True,
        partial=found.partial if found else False,
        listed=len(options),
        more=more,
        shown=shown,
        unit="trials" if chimera else "needs",
        met=team.cleared if chimera else sum(n.met for n in base_needs + extras),
        needs=len(team.objectives) if chimera else len(base_needs) + len(extras),
        score=percent(team.score),
        base_needs=base_needs,
        rows=form_rows(team, trials) if chimera else [],
        extras=extras,
        links=url.links(request.fill is not None, listing(more, shown or 1) if more else None),
    )


def stage_goals(
    enemies: Enemies, asks: FactionWars | ChimeraTrials | None, ask: TeamAsk
) -> tuple[Goals, dict[int, Trial], tuple[str, ...]]:
    """The goals; for the Chimera, its trials by skill (the objectives' keys) and where their
    needs disagree with the game's data."""
    match asks:
        case ChimeraTrials(difficulty=difficulty, column=column):
            brief = Brief(column, ask.wanted, ask.loadout, ask.counts, difficulty)
            return column_goals(enemies, brief)

        case FactionWars(challenge=picked):
            return finder_goals(ask.wanted, ask.counts, picked, ask.loadout.team_gear), {}, ()

        case None:
            return finder_goals(ask.wanted, ask.counts, None, ask.loadout.team_gear), {}, ()


def finder_goals(
    wanted: tuple[Tag, ...],
    counts: tuple[Distinct, ...],
    picked: Challenge | None,
    team_gear: tuple[Gear, ...],
) -> Goals:
    """The challenge's needs as an objective (those the gear any champion can wear meets made
    `Given`), what's asked besides as extras, all against the stage's enemies."""
    objectives = ()

    if picked and picked.needs:
        objectives = (Objective(1, ENEMIES, with_gear(picked.needs, team_gear)),)

    extras = tuple(AnyOf(frozenset({tag})) for tag in wanted) + counts
    return Goals(objectives, extras, ENEMIES, TEAM_SIZE)


def against_view(
    enemies: Enemies,
    base: Content,
    slots: tuple[Champion | None, ...],
    problems: tuple[str, ...],
) -> AgainstView:
    held = base.restriction if isinstance(base.restriction, Restriction) else None
    challenge_view = chimera = faction_url = None

    match base.asks:
        case FactionWars(challenge=picked):
            challenge_view = ChallengeView(picked.text, picked.checked) if picked else None
            challenge_view = challenge_view or ChallengeView(None, checked=False)

            if held and len(held.factions) == 1:
                faction_url = asset_url("factions", held.factions[0])  # the crypt's banner

        case ChimeraTrials(column=column, rotation=rotation):
            chimera = chimera_view(enemies, column, rotation, problems)

    return AgainstView(
        picker=base.picker,
        admits=restriction_label(held) if held else None,
        rotating=isinstance(base.restriction, Rotating),
        faction_url=faction_url,
        refused=[c.name for c in slots if held and c and not held.admits(c)],
        only=only_view(held) if held else None,
        challenge=challenge_view,
        chimera=chimera,
    )


def page_query(base: Content | None, min_grade: int) -> Query:
    """The page's own fields: the stage picked (the Chimera's column), the grade searched
    from."""
    picked: Query = ()

    if base:
        picked = (("base", "stage"), ("target", base.picker.target))

    if base and isinstance(base.asks, ChimeraTrials):
        picked += (("column", base.asks.column),)

    return (*picked, ("min_grade", str(min_grade)))


def stage_url(stage_id: int) -> str:
    return f"/teams?base=stage&target={stage_id}"


def gear_url(slots: list[SlotView], base: Content | None) -> str:
    """Its champions in Team gear's slots (open ones stay open), against the enemy picked
    (none: Team gear's default)."""
    fields = [(PAGE_FIELDS.slot, slot.choice) for slot in trimmed(slots)]

    if base:
        fields.append((PAGE_FIELDS.target, base.picker.target))

    return f"/team-gear?{urlencode(fields)}"


def option_view(
    number: int,
    team: Lineup,
    trials: dict[int, Trial],
    url: PageUrl,
    listed: int,
    base: Content | None,
) -> OptionView:
    """`trials`: the Chimera's by skill (else none); `url`: the page's, `listed` the options it
    lists (kept when it shows this one); `base`: the stage, Team gear's target."""
    slots = [slot_view(member, None) for member in team.slots]

    if trials:
        met, glanced = team.cleared, glance(form_rows(team, trials))
    else:
        covers = [n for cover in team.objectives for n in cover.needs] + list(team.extras)
        met, glanced = sum(n.met for n in covers), []

    return OptionView(
        number=number,
        slots=slots,
        met=met,
        score=percent(team.score),
        glance=glanced,
        show_url=url.to(url.team.slots, listing(listed, number)),
        use_url=url.to(slots),
        gear_url=gear_url(slots, base),
    )
