"""
app.py - the web entry point: routes that render the service's views as HTML. Only this
module and the templates know about HTTP or HTML; a JSON API would sit beside it.

- `app`, `templates`: the FastAPI app and its Jinja templates (uncached: edits show at once)
- `index`, `champion_list`, `lock`, `config`, `old_config`, `set_assumption`, `plan_glyph`,
  `reserve_rule`, `champion`, `builds`, `run`, `delete_run`, `equip`, `preview`, `accessories`,
  `accessory_weight`, `accessory_target`, `protect_accessory`, `sell_accessories`, `empower`,
  `chimera`, `targets`, `finder`, `info`, `sync`: the routes
- `read_form`, `find_champion`, `find_run`, `send_build`: what they share
- `static_url`: a static file's URL, changing whenever the file does (so no stale caches)
- `optimiser_url`: the nav's Optimiser link: the champion last solved for, else the list
- `CachedStatic`: the static files, cached by the browser (versioned URLs for good)
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.types import Scope

from optimiser.account import LOCK_LEVELS, Account, Champion
from optimiser.chimera.tags import NEVER_LANDS
from optimiser.reserve import reservations
from optimiser.teams.gear import gear_options
from optimiser.teams.kits import wantable
from webui import extractor, reader
from webui.forms.chimera import Unknown, parse_chimera
from webui.forms.common import FormErrors
from webui.forms.finder import GRADES as FINDER_GRADES
from webui.forms.finder import RARITIES as FINDER_RARITIES
from webui.forms.finder import parse_finder_query
from webui.forms.request import parse_equip, parse_request
from webui.forms.settings import (
    FlagSetting,
    GlyphPlan,
    ReserveSetting,
    WeightSetting,
    parse_flag,
    parse_glyph,
    parse_lock,
    parse_protect,
    parse_reserve_rule,
    parse_sell,
    parse_target_free,
    parse_weight,
)
from webui.forms.targets import TargetQuery, parse_target_query
from webui.forms.team import Offers
from webui.result import Err, Result, failed
from webui.service import accessories as accessory_pages
from webui.service import assumptions as assumption_pages
from webui.service import champions as champion_pages
from webui.service import chimera as chimera_pages
from webui.service import current, results, runs
from webui.service import empower as empower_pages
from webui.service import finder as finder_pages
from webui.service import info as info_pages
from webui.service import targets as target_pages

HERE = Path(__file__).resolve().parent


class CachedStatic(StaticFiles):
    """Static files with a `Cache-Control`: without one the browser revalidates every image on
    each page (the art's files are new after each extract, so heuristic freshness is short),
    and the tiles' frames and portraits pop in. A `static_url` (`?v=`) never changes; the art
    changes only when re-extracted, so a day's staleness is fine (a hard reload clears it)."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)

        if response.status_code == 200:
            versioned = b"v=" in scope.get("query_string", b"")
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable" if versioned else "public, max-age=86400"
            )

        return response


app = FastAPI(title="Raid optimiser")
app.mount("/static", CachedStatic(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
# No template cache: Jinja reloads a changed template but not the ones that import it (a page
# importing `_accessory.html`, which imports `_macros.html`, kept the old macros), so every
# render compiles afresh. Cheap at this size.
templates.env.cache = None
templates.env.globals["lock_levels"] = LOCK_LEVELS
templates.env.globals["static_url"] = lambda path: static_url(path)
templates.env.globals["synced_ago"] = reader.synced_ago
templates.env.globals["finder_rarities"] = FINDER_RARITIES
templates.env.globals["finder_grades"] = FINDER_GRADES
templates.env.globals["optimiser_url"] = lambda: optimiser_url()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    champions = champion_pages.search_champions(
        current.current_account(), current.current_locks(), ""
    )
    return templates.TemplateResponse(request, "index.html", {"champions": champions})


@app.get("/champions", response_class=HTMLResponse)
def champion_list(request: Request, query: str = ""):
    champions = champion_pages.search_champions(
        current.current_account(), current.current_locks(), query
    )
    return templates.TemplateResponse(request, "_champion_list.html", {"champions": champions})


@app.post("/champions/{champion_id}/lock", response_class=HTMLResponse)
async def lock(request: Request, champion_id: int):
    champion = find_champion(current.current_account(), champion_id)
    form = await read_form(request)

    match parse_lock(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case level:
            listed = champion_pages.lock_champion(champion, level)
            return templates.TemplateResponse(request, "_lock.html", {"listed": listed})


@app.get("/config", response_class=HTMLResponse)
def config(request: Request):
    """What solves assume and what gear they keep out (the store's settings)."""
    page = assumption_pages.assumptions_page(current.current_account())
    return templates.TemplateResponse(request, "assumptions.html", {"page": page})


@app.get("/assumptions")
def old_config():
    """The page's old address."""
    return RedirectResponse("/config", status_code=301)


@app.post("/assumptions", response_class=HTMLResponse)
async def set_assumption(request: Request):
    form = await read_form(request)

    match parse_flag(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case FlagSetting(flag=flag, on=on):
            view = assumption_pages.set_assumption(flag, on)
            return templates.TemplateResponse(request, "_flag.html", {"flag": view})


@app.post("/glyphs", response_class=HTMLResponse)
async def plan_glyph(request: Request):
    account = current.current_account()
    form = await read_form(request)

    match parse_glyph(form, account.tables):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case GlyphPlan(kind=kind, grade=grade):
            row = assumption_pages.plan_glyph_for(account, kind, grade)
            return templates.TemplateResponse(request, "_glyph_row.html", {"row": row})


@app.post("/reserve", response_class=HTMLResponse)
async def reserve_rule(request: Request):
    account = current.current_account()
    form = await read_form(request)

    match parse_reserve_rule(form, account):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case ReserveSetting(rule=rule, on=on):
            section = assumption_pages.change_reserve_rule(account, rule, on)
            return templates.TemplateResponse(request, "_reserve.html", {"reserve": section})


@app.get("/accessories", response_class=HTMLResponse)
def accessories(request: Request, tab: str = accessory_pages.ACCESSORY_TABS[0]):
    if tab not in accessory_pages.ACCESSORY_TABS:
        raise HTTPException(404, f"no tab {tab}")

    page = accessory_pages.accessories_page(current.current_account(), tab)
    return templates.TemplateResponse(request, "accessories.html", {"page": page})


@app.post("/accessories/weights", response_class=HTMLResponse)
async def accessory_weight(request: Request):
    form = await read_form(request)

    match parse_weight(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case WeightSetting(key=key, stat=stat, weight=weight):
            accessory_pages.change_type_weight(key, stat, weight)
            return HTMLResponse('<small class="up">Saved: the lists re-plan with it.</small>')


@app.post("/accessories/target", response_class=HTMLResponse)
async def accessory_target(request: Request):
    form = await read_form(request)

    match parse_target_free(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case target:
            plan = accessory_pages.set_target_free(current.current_account(), target)
            return templates.TemplateResponse(request, "_cleanup.html", {"plan": plan})


@app.post("/accessories/{artifact_id}/protect", response_class=HTMLResponse)
async def protect_accessory(request: Request, artifact_id: int):
    form = await read_form(request)
    plan = accessory_pages.protect_accessory(
        current.current_account(), artifact_id, parse_protect(form)
    )
    return templates.TemplateResponse(request, "_cleanup.html", {"plan": plan})


@app.post("/accessories/sell", response_class=HTMLResponse)
async def sell_accessories(request: Request):
    fields = [str(value) for value in (await request.form()).getlist("artifact_id")]

    match parse_sell(fields, accessory_pages.pieces_to_sell(current.current_account())):
        case FormErrors(messages=messages):
            outcome = Err("; ".join(messages))

        case artifact_ids:
            outcome = extractor.select_to_sell(artifact_ids)

    context = {
        "error": outcome.reason if failed(outcome) else None,
        "done": "Selected in game: check them and confirm the sale there.",
    }
    return templates.TemplateResponse(request, "_equip_result.html", context)


@app.get("/empower", response_class=HTMLResponse)
def empower(request: Request, rarity: str = empower_pages.DEFAULT_RARITY):
    account = current.current_account()
    if rarity not in empower_pages.empowerable_rarities(account):
        raise HTTPException(404, f"{rarity} champions can't be empowered")

    page = empower_pages.empower_page(account, rarity)
    return templates.TemplateResponse(request, "empower.html", {"page": page})


@app.get("/chimera", response_class=HTMLResponse)
def chimera(request: Request):
    account = current.current_account()
    sets, relics = current.current_effect_sources()
    offers = Offers(
        wantable(account, NEVER_LANDS), gear_options(account, sets, relics, NEVER_LANDS)
    )
    query = {name: request.query_params.getlist(name) for name in request.query_params}
    enemies = current.current_enemies()
    rotation = chimera_pages.rotation_column(account, enemies, datetime.now(UTC))

    match parse_chimera(query, account, offers, rotation):
        case Unknown(reason=reason):
            raise HTTPException(404, reason)
        case FormErrors(messages=messages):
            raise HTTPException(400, "; ".join(messages))
        case asked:
            page = chimera_pages.chimera_page(account, enemies, asked, offers, rotation)

    return templates.TemplateResponse(request, "chimera.html", {"page": page})


@app.get("/champions/{champion_id}", response_class=HTMLResponse)
def champion(request: Request, champion_id: int):
    account = current.current_account()
    page = champion_pages.champion_page(
        account, current.current_reserve_rules(), find_champion(account, champion_id)
    )
    picker = target_pages.target_picker(current.current_enemies(), TargetQuery())
    context = {"page": page, "picker": picker, "fill": False}
    return templates.TemplateResponse(request, "champion.html", context)


@app.get("/info", response_class=HTMLResponse)
def info(request: Request):
    page = info_pages.info_page(current.current_account(), current.current_enemies())
    return templates.TemplateResponse(request, "info.html", {"page": page})


@app.get("/targets", response_class=HTMLResponse)
def targets(request: Request):
    """The target picker after a change (htmx names the field changed); a saved target
    (`target=`) is shown without filling the page's fields in again."""
    query = parse_target_query(request.query_params, request.headers.get("HX-Trigger-Name"))
    picker = target_pages.target_picker(current.current_enemies(), query)
    context = {"picker": picker, "fill": query.target is None}
    return templates.TemplateResponse(request, "_target_picker.html", context)


@app.get("/finder", response_class=HTMLResponse)
def finder(request: Request):
    """The champion finder's list, for its query (`_finder.html` asks as the user types)."""
    view = finder_pages.find_champions(
        current.current_account(), parse_finder_query(request.query_params)
    )
    return templates.TemplateResponse(request, "_finder_results.html", {"finder": view})


@app.post("/champions/{champion_id}/builds", response_class=HTMLResponse)
async def builds(request: Request, champion_id: int):
    account = current.current_account()
    form = await read_form(request)

    champion = find_champion(account, champion_id)

    locks, rules = current.current_locks(), current.current_reserve_rules()

    match parse_request(form, champion, account, locks, rules):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case solve_request:
            outcome = results.solve(account, solve_request, reservations(account, rules))

    # The new run goes in the history too, swapped in beside the results.
    context = {
        "run": runs.record_run(account, form, solve_request, outcome),
        "history": runs.run_history(champion),
        "champion_id": champion.id,
        "history_oob": True,
    }
    return templates.TemplateResponse(request, "_run.html", context)


@app.get("/champions/{champion_id}/runs/{run_id}", response_class=HTMLResponse)
def run(request: Request, champion_id: int, run_id: int):
    champion = find_champion(current.current_account(), champion_id)
    context = {"run": find_run(champion, run_id)}
    return templates.TemplateResponse(request, "_run.html", context)


@app.delete("/champions/{champion_id}/runs/{run_id}", response_class=HTMLResponse)
def delete_run(request: Request, champion_id: int, run_id: int):
    champion = find_champion(current.current_account(), champion_id)
    runs.forget_run(champion, run_id)
    context = {"history": runs.run_history(champion), "champion_id": champion.id}
    return templates.TemplateResponse(request, "_history.html", context)


@app.post("/sync", response_class=HTMLResponse)
def sync(request: Request):
    """Reads the account; on success the page reloads with it (htmx's HX-Refresh)."""
    outcome = reader.sync()
    context = {"error": outcome.reason if failed(outcome) else None, "done": "Synced"}
    response = templates.TemplateResponse(request, "_equip_result.html", context)

    if not failed(outcome):
        response.headers["HX-Refresh"] = "true"

    return response


@app.post("/champions/{champion_id}/equip", response_class=HTMLResponse)
async def equip(request: Request, champion_id: int):
    def send(account: Account, champion: Champion, artifact_ids: list[int]):
        match extractor.equip(champion.id, artifact_ids):
            case Err() as error:
                return error

        match reader.sync():
            case Err(reason=reason):
                return Err(f"equipped, but the sync failed: {reason}")

        return None

    return await send_build(request, champion_id, send, "Equipped and synced.")


@app.post("/champions/{champion_id}/preview", response_class=HTMLResponse)
async def preview(request: Request, champion_id: int):
    def send(account: Account, champion: Champion, artifact_ids: list[int]):
        return extractor.preview(account, champion.id, artifact_ids)

    return await send_build(request, champion_id, send, "Previewing in game.")


async def send_build(
    request: Request,
    champion_id: int,
    send: Callable[[Account, Champion, list[int]], Result[None]],
    done: str,
) -> HTMLResponse:
    """The build button's pieces, sent to the game by `send`."""
    account = current.current_account()
    champion = find_champion(account, champion_id)
    form = await read_form(request)

    match parse_equip(form, account):
        case FormErrors(messages=messages):
            outcome = Err("; ".join(messages))

        case artifact_ids:
            outcome = send(account, champion, artifact_ids)

    context = {"error": outcome.reason if failed(outcome) else None, "done": done}
    return templates.TemplateResponse(request, "_equip_result.html", context)


async def read_form(request: Request) -> dict[str, str]:
    """The posted form's fields, each name's last value."""
    return {key: str(value) for key, value in (await request.form()).items()}


def find_champion(account: Account, champion_id: int) -> Champion:
    if (champion := account.champions.get(champion_id)) is None:
        raise HTTPException(404, f"no champion {champion_id}")

    return champion


def find_run(champion: Champion, run_id: int) -> runs.RunView:
    if (saved := runs.saved_run(champion, run_id)) is None:
        raise HTTPException(404, f"no run {run_id} for champion {champion.id}")

    return saved


def optimiser_url() -> str:
    if (champion_id := runs.last_solved()) is not None:
        return f"/champions/{champion_id}"

    return "/"


def static_url(path: str) -> str:
    modified = HERE.joinpath("static", path).stat().st_mtime_ns
    return f"/static/{path}?v={modified}"
