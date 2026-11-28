"""
champions.py - the champion list and each champion's optimiser: locks, solves and their runs,
stopping one, sending a build to the game (equip, preview), and the finder dialog's champions.

- `router`: its routes, `index`, `lock`, `champion`, `builds`, `stop_solve`, `delete_run`, `equip`,
  `preview`, `finder`
"""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from optimiser.account import LOCK_LEVELS, Account, Champion
from optimiser.reserve import reservations
from optimiser.solve import Stopped, stop
from webui import extractor, inertia, reader
from webui.forms.common import FormErrors
from webui.forms.request import Equip, parse_equip, parse_request
from webui.forms.settings import (
    parse_lock,
)
from webui.forms.targets import parse_target_query
from webui.responses import (
    back_with,
    find_champion,
    finder_query,
    inertia_page,
    read_form,
    sent,
    view_json,
)
from webui.result import Err, Result
from webui.service import champions as champion_pages
from webui.service import current, results, runs
from webui.service import finder as finder_pages
from webui.service import targets as target_pages

router = APIRouter()


@router.get("/")
def index(request: Request):
    """The champion list: the finder's list, as the filters in the query ask, each champion with
    their lock. Changing a filter reloads only `finder`."""
    query = finder_query(request)

    def finder() -> finder_pages.FinderView:
        return finder_pages.find_champions(
            current.current_account(), current.current_locks(), query
        )

    return inertia_page(request, "Champions", {"finder": finder, "lock_levels": list(LOCK_LEVELS)})


@router.post("/champions/{champion_id}/lock")
async def lock(request: Request, champion_id: int):
    """From the champion list; back to it (the list's own page, filters and all)."""
    champion = find_champion(current.current_account(), champion_id)
    form = await read_form(request)

    match parse_lock(form):
        case FormErrors(messages=messages):
            raise HTTPException(422, "; ".join(messages))

        case level:
            finder_pages.lock_champion(champion, level)
            return inertia.back(request)


@router.get("/champions/{champion_id}")
def champion(request: Request, champion_id: int, run: int | None = None):
    """The champion's optimiser, showing `run` (else the latest) with the target it was asked
    against; picking another run reloads `run` and `picker` alone."""
    account = current.current_account()
    picked = find_champion(account, champion_id)
    shown = champion_pages.shown_run(picked, run)
    target = (shown.form if shown else {}).get("target", "")

    def page() -> champion_pages.ChampionPage:
        return champion_pages.champion_page(account, current.current_reserve_rules(), picked)

    def picker() -> target_pages.TargetPicker:
        query = parse_target_query({"target": target}, None)
        return target_pages.target_picker(current.current_enemies(), query)

    return inertia_page(request, "Champion", {"page": page, "run": shown, "picker": picker})


@router.get("/finder")
def finder(request: Request):
    """The champions the filters match, as the finder dialog (`ChampionFinder.vue`) asks while
    the user types."""
    view = finder_pages.find_champions(
        current.current_account(), current.current_locks(), finder_query(request)
    )
    return view_json(view)


@router.post("/champions/{champion_id}/builds")
async def builds(request: Request, champion_id: int):
    """Solves, keeps the run, and shows it (a solve takes seconds to minutes)."""
    account = current.current_account()
    form = await read_form(request)
    champion = find_champion(account, champion_id)
    locks, rules = current.current_locks(), current.current_reserve_rules()

    match parse_request(form, champion, account, locks, rules):
        case FormErrors() as errors:
            return back_with(request, errors)

        case solve_request:
            # In a thread: the loop stays free to answer `/stop` meanwhile.
            reserved = reservations(account, rules)
            outcome = await run_in_threadpool(results.solve, account, solve_request, reserved)

    if isinstance(outcome, Stopped):
        return back_with(request, FormErrors(["Stopped before a build was found."]))

    kept = runs.record_run(account, form, solve_request, outcome)
    return inertia.redirect(f"/champions/{champion.id}?run={kept.entry.id}")


@router.post("/stop")
def stop_solve():
    """Stops the solve running (the champion page's or Team gear's): the champion page keeps
    the builds found by then."""
    stop()
    return JSONResponse({"error": None})


@router.delete("/champions/{champion_id}/runs/{run_id}")
def delete_run(request: Request, champion_id: int, run_id: int):
    champion = find_champion(current.current_account(), champion_id)
    runs.forget_run(champion, run_id)
    return inertia.back(request)


@router.post("/champions/{champion_id}/equip")
async def equip(request: Request, champion_id: int):
    """Refused when the account has moved on since the build was found: a piece now on a
    champion its gear rules keep it from (`results.check_equip`)."""

    def send(account: Account, champion: Champion, equip: Equip):
        if refused := results.check_equip(equip, account, champion):
            return Err(refused)

        match extractor.equip(champion.id, equip.artifact_ids):
            case Err() as error:
                return error

        match reader.sync():
            case Err(reason=reason):
                return Err(f"equipped, but the sync failed: {reason}")

        return None

    return await send_build(request, champion_id, send)


@router.post("/champions/{champion_id}/preview")
async def preview(request: Request, champion_id: int):
    def send(account: Account, champion: Champion, equip: Equip):
        return extractor.preview(account, champion.id, equip.artifact_ids)

    return await send_build(request, champion_id, send)


async def send_build(
    request: Request,
    champion_id: int,
    send: Callable[[Account, Champion, Equip], Result[None]],
) -> Response:
    """The build button's pieces, sent to the game by `send`."""
    account = current.current_account()
    champion = find_champion(account, champion_id)
    form = await read_form(request)

    match parse_equip(form, account, current.current_locks(), current.current_reserve_rules()):
        case FormErrors(messages=messages):
            outcome = Err("; ".join(messages))

        case equip:
            outcome = send(account, champion, equip)

    return sent(outcome)
