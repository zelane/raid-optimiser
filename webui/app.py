"""
app.py - the web entry point: routes that render the service's views as HTML. Only this
module and the templates know about HTTP or HTML; a JSON API would sit beside it.

- `app`, `templates`: the FastAPI app and its Jinja templates
- `index`, `champion_list`, `lock`, `assumptions`, `set_assumption`, `plan_glyph`, `champion`,
  `builds`, `run`, `delete_run`, `equip`, `preview`: the routes
- `find_champion`, `find_run`, `send_build`: what they share
- `static_url`: a static file's URL, changing whenever the file does (so no stale caches)
"""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from optimiser.account import Account, Champion
from optimiser.store import LOCK_LEVELS
from webui import extractor, service
from webui.forms import (
    FormErrors,
    parse_equip,
    parse_flag,
    parse_glyph,
    parse_lock,
    parse_request,
)

HERE = Path(__file__).resolve().parent

app = FastAPI(title="Raid optimiser")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["lock_levels"] = LOCK_LEVELS
templates.env.globals["palettes"] = {"default": "Default", "hana": "Hana"}  # palettes.css
templates.env.globals["static_url"] = lambda path: static_url(path)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    champions = service.search_champions(service.current_account(), service.current_locks(), "")
    return templates.TemplateResponse(request, "index.html", {"champions": champions})


@app.get("/champions", response_class=HTMLResponse)
def champion_list(request: Request, query: str = ""):
    champions = service.search_champions(service.current_account(), service.current_locks(), query)
    return templates.TemplateResponse(request, "_champion_list.html", {"champions": champions})


@app.post("/champions/{champion_id}/lock", response_class=HTMLResponse)
async def lock(request: Request, champion_id: int):
    champion = find_champion(service.current_account(), champion_id)
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_lock(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case level:
            listed = service.lock_champion(champion, level)
            return templates.TemplateResponse(request, "_lock.html", {"listed": listed})


@app.get("/assumptions", response_class=HTMLResponse)
def assumptions(request: Request):
    page = service.assumptions_page(service.current_account())
    return templates.TemplateResponse(request, "assumptions.html", {"page": page})


@app.post("/assumptions", response_class=HTMLResponse)
async def set_assumption(request: Request):
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_flag(form):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case flag, on:
            view = service.set_assumption(flag, on)
            return templates.TemplateResponse(request, "_flag.html", {"flag": view})


@app.post("/glyphs", response_class=HTMLResponse)
async def plan_glyph(request: Request):
    account = service.current_account()
    form = {key: str(value) for key, value in (await request.form()).items()}

    match parse_glyph(form, account.tables):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case kind, grade:
            row = service.plan_glyph_for(account, kind, grade)
            return templates.TemplateResponse(request, "_glyph_row.html", {"row": row})


@app.get("/champions/{champion_id}", response_class=HTMLResponse)
def champion(request: Request, champion_id: int):
    account = service.current_account()
    page = service.champion_page(
        account, service.current_locks(), find_champion(account, champion_id)
    )
    context = {"page": page}
    return templates.TemplateResponse(request, "champion.html", context)


@app.post("/champions/{champion_id}/builds", response_class=HTMLResponse)
async def builds(request: Request, champion_id: int):
    account = service.current_account()
    form = {key: str(value) for key, value in (await request.form()).items()}

    champion = find_champion(account, champion_id)

    match parse_request(form, champion, account, service.current_locks()):
        case FormErrors() as errors:
            return templates.TemplateResponse(request, "_errors.html", {"errors": errors})

        case solve_request:
            outcome = service.solve(account, solve_request)

    # The new run goes in the history too, swapped in beside the results.
    context = {
        "run": service.record_run(account, form, solve_request, outcome),
        "history": service.run_history(champion),
        "champion_id": champion.id,
        "history_oob": True,
    }
    return templates.TemplateResponse(request, "_run.html", context)


@app.get("/champions/{champion_id}/runs/{run_id}", response_class=HTMLResponse)
def run(request: Request, champion_id: int, run_id: int):
    champion = find_champion(service.current_account(), champion_id)
    context = {"run": find_run(champion, run_id)}
    return templates.TemplateResponse(request, "_run.html", context)


@app.delete("/champions/{champion_id}/runs/{run_id}", response_class=HTMLResponse)
def delete_run(request: Request, champion_id: int, run_id: int):
    champion = find_champion(service.current_account(), champion_id)
    service.forget_run(champion, run_id)
    context = {"history": service.run_history(champion), "champion_id": champion.id}
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
    account = service.current_account()
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


def find_run(champion: Champion, run_id: int) -> service.RunView:
    if (saved := service.saved_run(champion, run_id)) is None:
        raise HTTPException(404, f"no run {run_id} for champion {champion.id}")

    return saved


def static_url(path: str) -> str:
    modified = HERE.joinpath("static", path).stat().st_mtime_ns
    return f"/static/{path}?v={modified}"
