"""
app.py - the web entry point: routes that render the service's views as HTML. Only this
module and the templates know about HTTP or HTML; a JSON API would sit beside it.

- `app`, `templates`: the FastAPI app and its Jinja templates
- `index`, `champion_list`, `lock`, `assumptions`, `set_assumption`, `plan_glyph`, `champion`,
  `builds`, `run`, `delete_run`, `equip`, `preview`, `accessories`, `accessory_weight`,
  `accessory_target`, `protect_accessory`, `sell_accessories`, `empower`: the routes
- `find_champion`, `find_run`, `send_build`: what they share
- `static_url`: a static file's URL, changing whenever the file does (so no stale caches)
"""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from optimiser.account import LOCK_LEVELS, Account, Champion
from webui import extractor
from webui.forms import (
    FlagSetting,
    FormErrors,
    GlyphPlan,
    WeightSetting,
    parse_equip,
    parse_flag,
    parse_glyph,
    parse_lock,
    parse_protect,
    parse_request,
    parse_sell,
    parse_target_free,
    parse_weight,
)
from webui.service import accessories as accessory_pages
from webui.service import assumptions as assumption_pages
from webui.service import champions as champion_pages
from webui.service import current, results, runs
from webui.service import empower as empower_pages

HERE = Path(__file__).resolve().parent

app = FastAPI(title="Raid optimiser")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["lock_levels"] = LOCK_LEVELS
# palettes.css; a first visit (no cookie) gets Vault.
templates.env.globals["palettes"] = {"vault": "Vault", "default": "Pico", "hana": "Hana"}
templates.env.globals["default_palette"] = "vault"
templates.env.globals["static_url"] = lambda path: static_url(path)


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
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_lock(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case level:
            listed = champion_pages.lock_champion(champion, level)
            return templates.TemplateResponse(request, "_lock.html", {"listed": listed})


@app.get("/assumptions", response_class=HTMLResponse)
def assumptions(request: Request):
    page = assumption_pages.assumptions_page(current.current_account())
    return templates.TemplateResponse(request, "assumptions.html", {"page": page})


@app.post("/assumptions", response_class=HTMLResponse)
async def set_assumption(request: Request):
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_flag(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case FlagSetting(flag=flag, on=on):
            view = assumption_pages.set_assumption(flag, on)
            return templates.TemplateResponse(request, "_flag.html", {"flag": view})


@app.post("/glyphs", response_class=HTMLResponse)
async def plan_glyph(request: Request):
    account = current.current_account()
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_glyph(form, account.tables):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case GlyphPlan(kind=kind, grade=grade):
            row = assumption_pages.plan_glyph_for(account, kind, grade)
            return templates.TemplateResponse(request, "_glyph_row.html", {"row": row})


@app.get("/accessories", response_class=HTMLResponse)
def accessories(request: Request, tab: str = accessory_pages.ACCESSORY_TABS[0]):
    if tab not in accessory_pages.ACCESSORY_TABS:
        raise HTTPException(404, f"no tab {tab}")

    page = accessory_pages.accessories_page(current.current_account(), tab)
    return templates.TemplateResponse(request, "accessories.html", {"page": page})


@app.post("/accessories/weights", response_class=HTMLResponse)
async def accessory_weight(request: Request):
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_weight(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case WeightSetting(key=key, stat=stat, weight=weight):
            accessory_pages.change_type_weight(key, stat, weight)
            return HTMLResponse('<small class="up">Saved: the lists re-plan with it.</small>')


@app.post("/accessories/target", response_class=HTMLResponse)
async def accessory_target(request: Request):
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_target_free(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case target:
            plan = accessory_pages.set_target_free(current.current_account(), target)
            return templates.TemplateResponse(request, "_cleanup.html", {"plan": plan})


@app.post("/accessories/{artifact_id}/protect", response_class=HTMLResponse)
async def protect_accessory(request: Request, artifact_id: int):
    form = {key: str(value) for key, value in (await request.form()).items()}
    plan = accessory_pages.protect_accessory(
        current.current_account(), artifact_id, parse_protect(form)
    )
    return templates.TemplateResponse(request, "_cleanup.html", {"plan": plan})


@app.post("/accessories/sell", response_class=HTMLResponse)
async def sell_accessories(request: Request):
    fields = [str(value) for value in (await request.form()).getlist("artifact_id")]

    match parse_sell(fields, accessory_pages.pieces_to_sell(current.current_account())):
        case FormErrors(messages=messages):
            outcome = extractor.Err("; ".join(messages))

        case artifact_ids:
            outcome = extractor.select_to_sell(artifact_ids)

    context = {
        "error": outcome.reason if extractor.failed(outcome) else None,
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


@app.get("/champions/{champion_id}", response_class=HTMLResponse)
def champion(request: Request, champion_id: int):
    account = current.current_account()
    page = champion_pages.champion_page(
        account, current.current_locks(), find_champion(account, champion_id)
    )
    context = {"page": page}
    return templates.TemplateResponse(request, "champion.html", context)


@app.post("/champions/{champion_id}/builds", response_class=HTMLResponse)
async def builds(request: Request, champion_id: int):
    account = current.current_account()
    form = {key: str(value) for key, value in (await request.form()).items()}

    champion = find_champion(account, champion_id)

    match parse_request(form, champion, account, current.current_locks()):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case solve_request:
            outcome = results.solve(account, solve_request)

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


@app.post("/champions/{champion_id}/equip", response_class=HTMLResponse)
async def equip(request: Request, champion_id: int):
    def send(account: Account, champion: Champion, artifact_ids: list[int]):
        return extractor.equip(champion.id, artifact_ids)

    done = "Equipped. The next sync will show it here."
    return await send_build(request, champion_id, send, done)


@app.post("/champions/{champion_id}/preview", response_class=HTMLResponse)
async def preview(request: Request, champion_id: int):
    def send(account: Account, champion: Champion, artifact_ids: list[int]):
        return extractor.preview(account, champion.id, artifact_ids)

    return await send_build(request, champion_id, send, "Previewing in game.")


async def send_build(
    request: Request,
    champion_id: int,
    send: Callable[[Account, Champion, list[int]], extractor.Result[None]],
    done: str,
) -> HTMLResponse:
    """The build button's pieces, sent to the game by `send`."""
    account = current.current_account()
    champion = find_champion(account, champion_id)
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_equip(form, account):
        case FormErrors(messages=messages):
            outcome = extractor.Err("; ".join(messages))

        case artifact_ids:
            outcome = send(account, champion, artifact_ids)

    context = {"error": outcome.reason if extractor.failed(outcome) else None, "done": done}
    return templates.TemplateResponse(request, "_equip_result.html", context)


def find_champion(account: Account, champion_id: int) -> Champion:
    if (champion := account.champions.get(champion_id)) is None:
        raise HTTPException(404, f"no champion {champion_id}")

    return champion


def find_run(champion: Champion, run_id: int) -> runs.RunView:
    if (saved := runs.saved_run(champion, run_id)) is None:
        raise HTTPException(404, f"no run {run_id} for champion {champion.id}")

    return saved


def static_url(path: str) -> str:
    modified = HERE.joinpath("static", path).stat().st_mtime_ns
    return f"/static/{path}?v={modified}"
