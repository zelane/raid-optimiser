"""
sims.py - the sim page: a team against a stage on the game's own battle engine, and a run of it
(`webui.sims`, a minute or so: it runs in a worker thread, off the server's loop).

- `router`: its routes, `sims_page`, `sim_slot`, `sim_progress`, `run_sim`, `stop_sim`
- `run_and_record`: a run, recorded
"""

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from optimiser.account import SkillSettings
from webui import sims
from webui.forms.common import FormErrors
from webui.forms.sims import parse_sim_ask, parse_sim_run
from webui.forms.targets import parse_target_query
from webui.responses import find_champion, inertia_page, read_form, sent, view_json
from webui.result import Err, Result
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
    page = sim_pages.sim_page(account, asked.team, asked.runs, sims.running() is not None)
    return inertia_page(request, "Sims", {"page": page, "picker": picker})


@router.get("/sims/slot")
def sim_slot(champion: int, waves: int = 1):
    """A champion swapped into the team, as the page's slot (`TeamConfigurator.vue` asks):
    their skills, and auto's defaults for each of the stage's waves."""
    account = current.current_account()
    defaults = (SkillSettings({}),) * max(1, min(waves, 10))
    return view_json(sim_pages.slot_view(account, find_champion(account, champion), defaults))


@router.get("/sims/progress")
def sim_progress():
    """How far the sim under way has got (the page polls it while Run is going)."""
    return view_json(sim_pages.sim_progress(sims.running()))


@router.post("/sims/run")
async def run_sim(request: Request):
    """Runs the sim on the team as the page has it; the page reloads its results after."""
    account, form = current.current_account(), await read_form(request)
    picker = target_pages.target_picker(
        current.current_enemies(), parse_target_query({"target": form.get("target", "")}, None)
    )

    match parse_sim_run(form, account, picker.team_size):
        case FormErrors(messages=messages):
            return sent(Err("; ".join(messages)))
        case asked:
            pass

    sim = sims.Sim(picker.stage, picker.title, asked.slots, asked.ask.runs)
    team = sim_pages.team_label(account, asked.ask.team, asked.slots)
    return sent(await run_in_threadpool(run_and_record, sim, team))


def run_and_record(sim: sims.Sim, team: str) -> Result[None]:
    """The sim, its results summed up as soon as it ends: in the worker thread, so a page
    reloaded meanwhile (its request gone) still gets them."""
    match sims.run(sim, record=lambda: sim_pages.record_result(sim.title, team)):
        case Err() as failure:
            return failure
        case sims.Stopped(fights=0):
            return Err("stopped before a fight finished")
        case sims.Stopped() | sims.Finished():
            return None


@router.post("/sims/stop")
def stop_sim():
    """Ends the sim under way; its run answers with the fights done by then."""
    return sent(sims.stop())
