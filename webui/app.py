"""
app.py - the web entry point: routes that hand the service's views to Vue pages (Inertia,
`webui/inertia.py`), take forms and answer components' own requests as JSON. Only this module,
`inertia.py` and the page shell (`templates/inertia.html`) know about HTTP or HTML.

- `app`, `templates`: the FastAPI app and the shell's Jinja templates
- `index`, `lock`, `config`, `old_config`, `set_assumption`, `plan_glyph`,
  `reserve_rule`, `champion`, `builds`, `stop_solve`, `delete_run`, `equip`, `preview`,
  `accessories`, `accessory_type`, `add_accessory_type`, `copy_accessory_type`,
  `delete_accessory_type`, `accessory_target`, `protect_accessory`, `sell_accessories`, `empower`,
  `chimera`, `teams`, `team_gear`, `targets`, `finder`, `info`, `masteries`, `books`, `sync`:
  the routes
- `sent`, `saved`, `view_json`: a Vue component's own requests, answered as JSON
- `finder_query`: the champion filters in a request's query
- `back_with`: back to a Vue page's form with its errors
- `inertia_page`: a Vue page (`webui/frontend/src/pages`), with the props every page gets
- `read_form`, `find_champion`, `send_build`: what they share
- `static_url`: a static file's URL, changing whenever the file does (so no stale caches)
- `optimiser_url`: the nav's Optimiser link: the champion last solved for, else the list
- `CachedStatic`: the static files, cached by the browser (versioned URLs for good)
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.types import Scope

from optimiser.account import LOCK_LEVELS, Account, Champion
from optimiser.enemies import Restriction, team_restriction
from optimiser.reserve import reservations
from optimiser.solve import Stopped, stop
from optimiser.teams.gear import gear_options
from optimiser.teams.kits import wantable
from webui import extractor, inertia, reader
from webui.forms.books import parse_books_query
from webui.forms.common import FormErrors
from webui.forms.finder import FinderQuery, parse_finder_query
from webui.forms.request import parse_equip, parse_request
from webui.forms.settings import (
    FlagSetting,
    GlyphPlan,
    ReserveSetting,
    TypeEdit,
    parse_champion_type,
    parse_flag,
    parse_glyph,
    parse_lock,
    parse_off_target,
    parse_protect,
    parse_reserve_rule,
    parse_rule_value,
    parse_sell,
    parse_set_rule,
    parse_set_target,
    parse_set_value,
    parse_target_free,
)
from webui.forms.targets import TargetQuery, parse_target_query
from webui.forms.team import Offers
from webui.forms.team_gear import parse_gear_ask
from webui.forms.teams import parse_against, parse_teams
from webui.result import Err, Result, failed
from webui.service import accessories as accessory_pages
from webui.service import assumptions as assumption_pages
from webui.service import books as book_pages
from webui.service import champions as champion_pages
from webui.service import chimera as chimera_pages
from webui.service import current, layout, results, runs
from webui.service import empower as empower_pages
from webui.service import finder as finder_pages
from webui.service import info as info_pages
from webui.service import masteries as mastery_pages
from webui.service import targets as target_pages
from webui.service import team_gear as team_gear_pages
from webui.service import teams as teams_pages

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
templates.env.globals["static_url"] = lambda path: static_url(path)


@app.get("/")
def index(request: Request):
    """The champion list: the finder's list, as the filters in the query ask, each champion with
    their lock. Changing a filter reloads only `finder`."""
    query = finder_query(request)

    def finder() -> finder_pages.FinderView:
        return finder_pages.find_champions(
            current.current_account(), current.current_locks(), query
        )

    return inertia_page(request, "Champions", {"finder": finder, "lock_levels": list(LOCK_LEVELS)})


@app.get("/palette")
def palette(request: Request):
    """The theme's colours and the shared components, for checking the palette in place: a
    champion of each rarity the account has."""
    view = finder_pages.find_champions(
        current.current_account(), current.current_locks(), FinderQuery()
    )
    by_rarity = {}

    for row in view.picks:
        by_rarity.setdefault(row.champion.rarity, row.champion)

    return inertia_page(request, "Palette", {"champions": list(by_rarity.values())})


@app.post("/champions/{champion_id}/lock")
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


@app.get("/config")
def config(request: Request):
    """What solves assume and what gear they keep out (the store's settings)."""
    page = assumption_pages.assumptions_page(current.current_account())
    return inertia_page(request, "Config", {"page": page})


@app.get("/assumptions")
def old_config():
    """The page's old address."""
    return RedirectResponse("/config", status_code=301)


@app.post("/assumptions")
async def set_assumption(request: Request):
    form = await read_form(request)

    match parse_flag(form):
        case FormErrors() as errors:
            return back_with(request, errors)

        case FlagSetting(flag=flag, on=on):
            assumption_pages.set_assumption(flag, on)
            return inertia.back(request)


@app.post("/glyphs")
async def plan_glyph(request: Request):
    account = current.current_account()
    form = await read_form(request)

    match parse_glyph(form, account.tables):
        case FormErrors() as errors:
            return back_with(request, errors)

        case GlyphPlan(kind=kind, grade=grade):
            assumption_pages.plan_glyph_for(kind, grade)
            return inertia.back(request)


@app.post("/reserve")
async def reserve_rule(request: Request):
    account = current.current_account()
    form = await read_form(request)

    match parse_reserve_rule(form, account):
        case FormErrors() as errors:
            return back_with(request, errors)

        case ReserveSetting(rule=rule, on=on):
            assumption_pages.change_reserve_rule(rule, on)
            return inertia.back(request)


@app.get("/accessories")
def accessories(request: Request, tab: str = accessory_pages.ACCESSORY_TABS[0]):
    if tab not in accessory_pages.ACCESSORY_TABS:
        raise HTTPException(404, f"no tab {tab}")

    page = accessory_pages.accessories_page(current.current_account(), tab)
    return inertia_page(request, "Accessories", {"page": page})


WEIGHTS_TAB = "/accessories?tab=weights"


@app.post("/accessories/types")
async def accessory_type(request: Request):
    """A type's row, saved whole on each change; the lists re-plan with it on the next visit
    (rescoring is slow, so the page doesn't reload)."""
    account, form = current.current_account(), await read_form(request)

    match parse_champion_type(form, accessory_pages.type_factions(account)):
        case FormErrors() as errors:
            return saved(errors)

        case TypeEdit() as edit if accessory_pages.save_type(account, edit):
            return saved(None)

        case TypeEdit():
            return saved(FormErrors(["that type is gone; reload the page"]))


@app.post("/accessories/types/add")
def add_accessory_type():
    accessory_pages.add_type()
    return inertia.redirect(WEIGHTS_TAB)


@app.post("/accessories/types/{key}/copy")
def copy_accessory_type(key: str):
    accessory_pages.copy_type(current.current_account(), key)
    return inertia.redirect(WEIGHTS_TAB)


@app.post("/accessories/types/{key}/delete")
def delete_accessory_type(key: str):
    accessory_pages.delete_type(key)
    return inertia.redirect(WEIGHTS_TAB)


@app.post("/accessories/sets/value")
async def accessory_set_value(request: Request):
    match parse_set_value(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case value:
            accessory_pages.save_set_value(current.current_account(), value.set_id, value.factor)
            return saved(None)


@app.post("/accessories/sets/target")
async def accessory_set_target(request: Request):
    account, form = current.current_account(), await read_form(request)
    type_keys = {t.key for t in accessory_pages.current_types(account)}

    match parse_set_target(form, type_keys):
        case FormErrors() as errors:
            return saved(errors)

        case target:
            accessory_pages.save_set_target(account, target.set_id, target.type_key, target.on)
            return saved(None)


@app.post("/accessories/sets/rule")
async def accessory_set_rule(request: Request):
    match parse_set_rule(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case rule:
            accessory_pages.save_set_rule(
                current.current_account(), rule.set_id, rule.name, rule.value
            )
            return saved(None)


@app.post("/accessories/rule")
async def accessory_rule(request: Request):
    match parse_rule_value(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case rule:
            accessory_pages.save_rule(rule.name, rule.value)
            return saved(None)


@app.post("/accessories/off-target")
async def accessory_off_target(request: Request):
    match parse_off_target(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case share:
            accessory_pages.save_off_target(share)
            return saved(None)


@app.post("/accessories/target")
async def accessory_target(request: Request):
    """The clean-up's spaces to leave free; back to the page, re-planned."""
    match parse_target_free(await read_form(request)):
        case FormErrors() as errors:
            return back_with(request, errors)

        case target:
            accessory_pages.set_target_free(target)
            return inertia.back(request)


@app.post("/accessories/{artifact_id}/protect")
async def protect_accessory(request: Request, artifact_id: int):
    form = await read_form(request)
    accessory_pages.protect_accessory(artifact_id, parse_protect(form))
    return inertia.back(request)


@app.post("/accessories/sell")
async def sell_accessories(request: Request):
    """Selects the pieces in the game's sell screen; the user confirms the sale there."""
    fields = [str(value) for value in (await request.form()).getlist("artifact_id")]

    match parse_sell(fields, accessory_pages.pieces_to_sell(current.current_account())):
        case FormErrors(messages=messages):
            outcome = Err("; ".join(messages))

        case artifact_ids:
            outcome = extractor.select_to_sell(artifact_ids)

    return sent(outcome)


@app.get("/empower")
def empower(request: Request, rarity: str = empower_pages.DEFAULT_RARITY):
    account = current.current_account()
    if rarity not in empower_pages.empowerable_rarities(account):
        raise HTTPException(404, f"{rarity} champions can't be empowered")

    page = empower_pages.empower_page(account, rarity)
    return inertia_page(request, "Empower", {"page": page})


@app.get("/chimera")
def chimera(request: Request):
    """The Chimera's trials, once a page of their own: the team finder at the Chimera's
    hardest tier, the rest of the query kept."""
    picker = target_pages.target_picker(current.current_enemies(), TargetQuery(zone="Chimera"))
    kept = [(k, v) for k, v in request.query_params.multi_items() if k not in ("base", "target")]
    query = urlencode([("base", "stage"), ("target", picker.target), *kept])
    return RedirectResponse(f"/teams?{query}", status_code=308)


@app.get("/teams")
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


@app.get("/team-gear")
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


@app.get("/champions/{champion_id}")
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


@app.get("/info")
def info(request: Request):
    page = info_pages.info_page(current.current_account(), current.current_enemies())
    return inertia_page(request, "Info", {"page": page})


@app.get("/masteries")
def masteries(request: Request):
    page = mastery_pages.masteries_page(current.current_account())
    return inertia_page(request, "Masteries", {"page": page})


@app.get("/books")
def books(request: Request):
    """The champions short of skill books, as the champion filter bar narrows them:
    rarity and stars start at their `forms.books` defaults, the rest of the bar at any."""
    query = parse_books_query(request.query_params)
    page = book_pages.books_page(current.current_account(), query)
    return inertia_page(request, "Books", {"page": page})


@app.get("/targets")
def targets(request: Request):
    """The target picker (`TargetPicker.vue`) after a change: `changed` names the field
    changed (the levels under it go back to their defaults)."""
    query = parse_target_query(request.query_params, request.query_params.get("changed"))
    return view_json(target_pages.target_picker(current.current_enemies(), query))


@app.get("/finder")
def finder(request: Request):
    """The champions the filters match, as the finder dialog (`ChampionFinder.vue`) asks while
    the user types."""
    view = finder_pages.find_champions(
        current.current_account(), current.current_locks(), finder_query(request)
    )
    return view_json(view)


@app.post("/champions/{champion_id}/builds")
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


@app.post("/stop")
def stop_solve():
    """Stops the solve running (the champion page's or Team gear's): the champion page keeps
    the builds found by then."""
    stop()
    return JSONResponse({"error": None})


@app.delete("/champions/{champion_id}/runs/{run_id}")
def delete_run(request: Request, champion_id: int, run_id: int):
    champion = find_champion(current.current_account(), champion_id)
    runs.forget_run(champion, run_id)
    return inertia.back(request)


@app.post("/sync")
def sync():
    """Reads the account; on success the layout reloads its page's props with it."""
    return sent(reader.sync())


@app.post("/champions/{champion_id}/equip")
async def equip(request: Request, champion_id: int):
    def send(account: Account, champion: Champion, artifact_ids: list[int]):
        match extractor.equip(champion.id, artifact_ids):
            case Err() as error:
                return error

        match reader.sync():
            case Err(reason=reason):
                return Err(f"equipped, but the sync failed: {reason}")

        return None

    return await send_build(request, champion_id, send)


@app.post("/champions/{champion_id}/preview")
async def preview(request: Request, champion_id: int):
    def send(account: Account, champion: Champion, artifact_ids: list[int]):
        return extractor.preview(account, champion.id, artifact_ids)

    return await send_build(request, champion_id, send)


async def send_build(
    request: Request,
    champion_id: int,
    send: Callable[[Account, Champion, list[int]], Result[None]],
) -> Response:
    """The build button's pieces, sent to the game by `send`."""
    account = current.current_account()
    champion = find_champion(account, champion_id)
    form = await read_form(request)

    match parse_equip(form, account):
        case FormErrors(messages=messages):
            outcome = Err("; ".join(messages))

        case artifact_ids:
            outcome = send(account, champion, artifact_ids)

    return sent(outcome)


def sent(outcome: Result[None]) -> JSONResponse:
    """A command to the game, done or why not."""
    return JSONResponse({"error": outcome.reason if failed(outcome) else None})


def saved(errors: FormErrors | None) -> JSONResponse:
    """A setting saved in place (no reload): what was wrong, or null."""
    return JSONResponse({"error": "; ".join(errors.messages) if errors else None})


def view_json(view: object) -> Response:
    return Response(inertia.to_json(view), media_type="application/json")


def finder_query(request: Request) -> FinderQuery:
    lists = {name: request.query_params.getlist(name) for name in request.query_params}
    return parse_finder_query(request.query_params, lists)


def back_with(request: Request, errors: FormErrors) -> Response:
    """Back to the form's page, its errors shown there (the layout's alert)."""
    return inertia.back(request, {"form": "; ".join(errors.messages)})


def inertia_page(request: Request, component: str, props: inertia.Props) -> Response:
    """A Vue page, with what every page gets: the frame's nav and sync age."""

    def frame() -> layout.Layout:
        return layout.layout_view(request.url.path, optimiser_url(), reader.synced_ago())

    return inertia.respond(request, templates, component, {"layout": frame, **props})


async def read_form(request: Request) -> dict[str, str]:
    """The posted form's fields, each name's last value."""
    return {key: str(value) for key, value in (await request.form()).items()}


def find_champion(account: Account, champion_id: int) -> Champion:
    if (champion := account.champions.get(champion_id)) is None:
        raise HTTPException(404, f"no champion {champion_id}")

    return champion


def optimiser_url() -> str:
    if (champion_id := runs.last_solved()) is not None:
        return f"/champions/{champion_id}"

    return "/"


def static_url(path: str) -> str:
    modified = HERE.joinpath("static", path).stat().st_mtime_ns
    return f"/static/{path}?v={modified}"
