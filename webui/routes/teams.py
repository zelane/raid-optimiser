"""
teams.py - the team finder (the Chimera's old address goes to it), Team gear, and the target
picker's changes.

- `router`: its routes, `chimera`, `teams`, `team_gear`, `targets`
"""

from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from optimiser.enemies import Restriction, team_restriction
from optimiser.teams.gear import gear_options
from optimiser.teams.kits import wantable
from webui.forms.common import FormErrors
from webui.forms.targets import TargetQuery, parse_target_query
from webui.forms.team import Offers
from webui.forms.team_gear import parse_gear_ask
from webui.forms.teams import parse_against, parse_teams
from webui.responses import (
    inertia_page,
    view_json,
)
from webui.service import chimera as chimera_pages
from webui.service import current
from webui.service import finder as finder_pages
from webui.service import targets as target_pages
from webui.service import team_gear as team_gear_pages
from webui.service import teams as teams_pages

router = APIRouter()


@router.get("/chimera")
def chimera(request: Request):
    """The Chimera's trials, once a page of their own: the team finder at the Chimera's
    hardest tier, the rest of the query kept."""
    picker = target_pages.target_picker(current.current_enemies(), TargetQuery(zone="Chimera"))
    kept = [(k, v) for k, v in request.query_params.multi_items() if k not in ("base", "target")]
    query = urlencode([("base", "stage"), ("target", picker.target), *kept])
    return RedirectResponse(f"/teams?{query}", status_code=308)


@router.get("/teams")
def teams(request: Request):
    """The team finder: a stage's needs (a Faction Wars challenge, the Chimera's trials), or
    none, and what's asked besides."""
    account = current.current_account()
    enemies = current.current_enemies()
    sets, relics = current.current_effect_sources()
    query = {name: request.query_params.getlist(name) for name in request.query_params}
    rotation = chimera_pages.rotation_column(account, enemies, datetime.now(UTC))
    base = teams_pages.content(enemies, parse_against(query), rotation)
    never = teams_pages.never_lands(base)
    offers = Offers(wantable(account, never), gear_options(account, sets, relics, never), relics)

    match parse_teams(query, account, offers):
        case FormErrors(messages=messages):
            raise HTTPException(400, "; ".join(messages))
        case asked:
            page = teams_pages.teams_page(account, enemies, base, asked, offers)

    return inertia_page(request, "Teams", {"page": page})


@router.get("/team-gear")
def team_gear(request: Request):
    """A team's gear against one target: solved when the query says `run`."""
    account = current.current_account()
    rules = current.current_reserve_rules()
    query = {name: request.query_params.getlist(name) for name in request.query_params}

    match parse_gear_ask(query, account, rules, current.current_locks()):
        case FormErrors(messages=messages):
            raise HTTPException(400, "; ".join(messages))
        case asked:
            pass

    enemies = current.current_enemies()
    target = parse_target_query({"target": (query.get("target") or [""])[-1]}, None)
    picker = target_pages.target_picker(enemies, target)
    stage = enemies.stages[picker.stage]
    restriction = team_restriction(stage)
    page = team_gear_pages.gear_page(
        account, asked, rules, picker.picked, picker.title, restriction
    )
    only = finder_pages.only_view(restriction) if isinstance(restriction, Restriction) else None
    return inertia_page(request, "TeamGear", {"page": page, "picker": picker, "only": only})


@router.get("/targets")
def targets(request: Request):
    """The target picker (`TargetPicker.vue`) after a change: `changed` names the field
    changed (the levels under it go back to their defaults)."""
    query = parse_target_query(request.query_params, request.query_params.get("changed"))
    return view_json(target_pages.target_picker(current.current_enemies(), query))
