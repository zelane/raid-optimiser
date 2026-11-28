"""
sims.py - running a sim from the web UI: `just sim` (the battle host, the game's own engine, on
a saved team against a stage; the justfile knows the paths), one at a time, then a record of
what it was of beside its results (`paths.LAST_SIM`), for the page to show with them.

- `TIMEOUT`: how long a sim may take (300 fights take about 40 s, plus building the team)
- `Sim`: what's simmed
- `run`: the sim, done or why not
"""

import json
import subprocess
import threading
from dataclasses import asdict, dataclass

from optimiser.paths import LAST_SIM, ROOT
from webui.result import Err, Result

TIMEOUT = 1800.0
LINES = 3  # of the sim's output, kept as the reason it failed

_running = threading.Lock()


@dataclass(frozen=True)
class Sim:
    """A saved team (`preset`: its champions and skill settings) against a stage, `seeds` times;
    `title` names the stage as the target picker does."""

    stage: int
    title: str
    preset: int
    champion_ids: tuple[int, ...]
    seeds: int


def run(sim: Sim) -> Result[None]:
    if not _running.acquire(blocking=False):
        return Err("a sim is already running")

    try:
        champions = ",".join(str(i) for i in sim.champion_ids)
        command = ["just", "sim", str(sim.stage), champions, str(sim.seeds), str(sim.preset)]
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError:
        return Err("`just` isn't on the web server's PATH")
    except subprocess.TimeoutExpired:
        return Err(f"the sim took over {TIMEOUT:g} s")
    finally:
        _running.release()

    if done.returncode != 0:
        lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
        return Err(" / ".join(lines[-LINES:]) or f"`just sim` exited {done.returncode}")

    LAST_SIM.write_text(json.dumps(asdict(sim)))
    return None
