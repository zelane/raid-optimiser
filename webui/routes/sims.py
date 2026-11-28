"""
sims.py - the sim page: a saved team against a stage on the game's own battle engine, and a run
of it (`webui.sims`, a minute or so: it runs in a worker thread, off the server's loop).

- `router`: its routes, `sims`, `run_sim`
"""

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from webui import sims
from webui.forms.common import FormErrors
from webui.forms.sims import parse_sim_ask
from webui.forms.targets import parse_target_query
from webui.responses import inertia_page, read_form, sent
from webui.result import Err
from webui.service import current
from webui.service import sims as sim_pages
from webui.service import targets as target_pages

router = APIRouter()


@router.get("/sims")
def sims_page(request: Request):
    """The opponent (the target picker's stage), the saved team, how many runs, and the last
    sim's results."""
    account = current.current_account()

    match parse_sim_ask(request.query_params, account):
        case FormErrors(messages=messages):
            raise HTTPException(400, "; ".join(messages))
        case asked:
            pass

    picker = target_pages.target_picker(
        current.current_enemies(), parse_target_query({"target": asked.target}, None)
    )
    page = sim_pages.sim_page(account, asked.team, asked.runs)
    return inertia_page(request, "Sims", {"page": page, "picker": picker})


@router.post("/sims/run")
async def run_sim(request: Request):
    """Runs the sim; the page reloads its results after."""
    account, form = current.current_account(), await read_form(request)

    match parse_sim_ask(form, account):
        case FormErrors(messages=messages):
            return sent(Err("; ".join(messages)))
        case asked if asked.team is None:
            return sent(Err("pick a saved team"))
        case asked:
            pass

    picker = target_pages.target_picker(
        current.current_enemies(), parse_target_query({"target": asked.target}, None)
    )
    preset = account.preset(asked.team)
    assert preset is not None  # parse_sim_ask checked it
    sim = sims.Sim(picker.stage, picker.title, preset.id, preset.champion_ids, asked.runs)
    return sent(await run_in_threadpool(sims.run, sim))
