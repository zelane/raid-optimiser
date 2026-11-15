"""
teams.py - the team finder page: the base needs (a Faction Wars stage's challenge, or none),
what every team must bring besides (tags, so many different debuffs or buffs) and the gear it
may count on, the team's slots, the teams the search finds (every way to bring it all, listed
a few at a time) and, for the team shown, who brings what.

- `MORE`: how many more teams "show more" lists
- `CryptOption`, `BaseView`, `OptionView`, `TeamsPage`: the views
- `teams_page`: what the page asks for
- `finder_goals`, `base_view`, `option_view`: its pieces
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.enemies import Enemies
from optimiser.factionwars import ENEMIES, Challenge, Crypt, admits, challenge
from optimiser.teams.cover import Lineup
from optimiser.teams.find import check_slots, find_teams
from optimiser.teams.gear import Gear, with_gear
from optimiser.teams.kits import candidates
from optimiser.teams.needs import AnyOf, Distinct, Goals, Objective
from optimiser.teams.tags import Tag
from webui.forms.team import GRADES, Fill, Offers
from webui.forms.teams import TEAM_SIZE, FactionWarsBase, TeamsRequest
from webui.service.team import (
    NeedView,
    SlotView,
    TeamView,
    need_view,
    percent,
    slot_view,
    slot_worn,
    team_view,
)
from webui.service.views import asset_url

MORE = 9  # teams each "show more" adds


@dataclass(frozen=True)
class CryptOption:
    region: str
    name: str
    selected: bool


@dataclass(frozen=True)
class BaseView:
    """The base needs as picked: `kind` ("fw", or "" for none), the crypts and the stage
    numbers to pick from, the challenge's text (`checked`: the finder reads it; else nothing is
    asked of the team for it), the crypt's faction (only its champions are searched) and the
    slots' champions it doesn't admit."""

    kind: str
    crypts: list[CryptOption]
    difficulty: str
    stages: int
    number: int
    challenge: str | None
    checked: bool
    faction: str | None
    faction_url: str | None
    refused: list[str]


@dataclass(frozen=True)
class OptionView:
    """A team the search found: its slots, how many needs it meets, its score (%)."""

    number: int  # 1 first
    slots: list[SlotView]
    met: int
    score: int


@dataclass(frozen=True)
class TeamsPage:
    base: BaseView
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
    met: int  # needs the team shown meets
    needs: int  # needs in all
    score: int  # % of what's shown
    base_needs: list[NeedView]  # the challenge's, for the team shown
    extras: list[NeedView]  # what's asked besides, for the team shown


def teams_page(
    account: Account,
    enemies: Enemies,
    crypts: tuple[Crypt, ...],
    request: TeamsRequest,
    offers: Offers,
) -> TeamsPage:
    """With `request.fill` (and something needed), the search fills the open slots every way
    it can, from the crypt's faction for a Faction Wars stage; else the slots are shown as
    they are."""
    ask = request.team
    base = request.base
    picked = challenge(enemies.stages[base.stage]) if base else None
    goals = finder_goals(ask.wanted, ask.counts, picked, ask.loadout.team_gear)
    asked = bool(goals.requirements)
    slots = tuple(pick if isinstance(pick, Champion) else None for pick in ask.picks)
    worn = slot_worn(account, ask, offers, slots)

    match request.fill:
        case Fill(listed=listed, option=option) if asked:
            pool = candidates(account, request.min_grade)

            if base:
                pool = [c for c in pool if admits(base.crypt, c)]

            found = find_teams(account, ask.loadout, slots, goals, pool, listed, worn)
            lineup, options = found.lineup, found.options
        case _:
            listed, option, found = 0, 1, None
            lineup, options = check_slots(account, ask.loadout, slots, goals, worn), ()

    shown = option if 1 <= option <= len(options) else (1 if options else None)
    team = options[shown - 1] if shown else lineup
    base_needs = [need_view(n) for cover in team.objectives for n in cover.needs]
    extras = [need_view(n) for n in team.extras]
    total = found.found if found else 0
    return TeamsPage(
        base=base_view(base, picked, crypts, slots),
        min_grade=request.min_grade,
        grades=GRADES,
        team=team_view(account, lineup.slots, ask, offers, "the enemies"),
        ran=request.fill is not None,
        asked=asked,
        candidates=found.candidates if found else 0,
        options=[option_view(number, o) for number, o in enumerate(options, 1)],
        found=total,
        complete=found.complete if found else True,
        partial=found.partial if found else False,
        listed=len(options),
        more=min(listed + MORE, total) if total > listed else 0,
        shown=shown,
        met=sum(n.met for n in base_needs + extras),
        needs=len(base_needs) + len(extras),
        score=percent(team.score),
        base_needs=base_needs,
        extras=extras,
    )


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


def base_view(
    base: FactionWarsBase | None,
    picked: Challenge | None,
    crypts: tuple[Crypt, ...],
    slots: tuple[Champion | None, ...],
) -> BaseView:
    crypt = base.crypt if base else crypts[0]
    difficulty = base.difficulty if base else list(crypt.stages)[-1]
    return BaseView(
        kind="fw" if base else "",
        crypts=[CryptOption(c.region, c.name, c is crypt) for c in crypts],
        difficulty=difficulty,
        stages=len(crypt.stages[difficulty]),
        number=base.number if base else 1,
        challenge=picked.text if picked else None,
        checked=bool(picked and picked.checked),
        faction=crypt.faction if base else None,
        faction_url=asset_url("factions", crypt.faction) if base else None,
        refused=[c.name for c in slots if base and c and not admits(base.crypt, c)],
    )


def option_view(number: int, team: Lineup) -> OptionView:
    covers = [n for cover in team.objectives for n in cover.needs] + list(team.extras)
    return OptionView(
        number=number,
        slots=[slot_view(member, None) for member in team.slots],
        met=sum(n.met for n in covers),
        score=percent(team.score),
    )
