"""
sims.py - running a sim from the web UI: `just sim` (the battle host, the game's own engine, on
a team against a stage; the justfile knows the paths), one at a time, the team's skill settings
passed in a file (`paths.SIM_TEAM`, in a saved team's shape). The page sums its results up as
soon as it's done (`service.sims.record_result`).

- `TIMEOUT`: how long a sim may take (300 fights take about 40 s, plus building the team)
- `Sim`: what's simmed
- `Running`, `running`: the sim under way, if one is (for its progress)
- `Finished`, `Stopped`, `Outcome`: how a sim ended
- `run`: the sim, done, stopped or why not, its results recorded while it still counts as running
- `fight`: its fights (`just sim`)
- `stop`: ends the sim under way (its host processes, a process group of their own)
- `settings_json`: the team's skill settings, as the snapshot keeps a saved team's
"""

import json
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from optimiser.paths import HOST_RESULTS, ROOT, SIM_TEAM
from webui.forms.sims import SlotAsk
from webui.result import Err, Result

TIMEOUT = 1800.0
LINES = 3  # of the sim's output, kept as the reason it failed

_running = threading.Lock()


@dataclass(frozen=True)
class Sim:
    """A team (its champions and their skill settings) against a stage, `seeds` times; `title`
    names the stage as the target picker does."""

    stage: int
    title: str
    slots: tuple[SlotAsk, ...]
    seeds: int


@dataclass(frozen=True)
class Running:
    seeds: int
    started: float  # time.time()
    summing: bool = False  # the fights are over, their results being summed up


@dataclass(frozen=True)
class Finished:
    pass


@dataclass(frozen=True)
class Stopped:
    fights: int  # done before it was stopped, their results kept


type Outcome = Finished | Stopped | Err

_under_way: Running | None = None
_process: subprocess.Popen | None = None
_stop_asked = threading.Event()


def running() -> Running | None:
    return _under_way


def run(sim: Sim, record: Callable[[], None]) -> Outcome:
    """The sim; once fights are done (all, or those before a stop), `record` sums them up while
    the sim still counts as running, so a page waiting on it finds its results (a Hydra fight's
    results are large: summing 100 up takes a while)."""
    global _under_way

    if not _running.acquire(blocking=False):
        return Err("a sim is already running")

    _under_way = Running(sim.seeds, time.time())
    _stop_asked.clear()

    try:
        outcome = fight(sim)

        if isinstance(outcome, Finished) or (isinstance(outcome, Stopped) and outcome.fights):
            _under_way = replace(_under_way, summing=True)
            record()

        return outcome
    finally:
        _under_way = None
        _running.release()


def fight(sim: Sim) -> Outcome:
    """`just sim` on the team, in a process group of its own (for `stop`)."""
    global _process

    try:
        SIM_TEAM.write_text(json.dumps(settings_json(sim.slots)))
        champions = ",".join(str(slot.champion_id) for slot in sim.slots)
        command = ["just", "sim", str(sim.stage), champions, str(sim.seeds), str(SIM_TEAM)]
        _process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        output, _ = _process.communicate(timeout=TIMEOUT)
    except FileNotFoundError:
        return Err("`just` isn't on the web server's PATH")
    except subprocess.TimeoutExpired:
        end_group(_process)
        return Err(f"the sim took over {TIMEOUT:g} s")
    finally:
        returncode = _process.returncode if _process else None
        _process = None

    if _stop_asked.is_set():
        return Stopped(keep_whole_results())

    if returncode != 0:
        lines = [line for line in output.splitlines() if line.strip()]
        return Err(" / ".join(lines[-LINES:]) or f"`just sim` exited {returncode}")

    return Finished()


def stop() -> Result[None]:
    if (process := _process) is None:
        return Err("no sim is running")

    _stop_asked.set()
    end_group(process)
    return None


def end_group(process: subprocess.Popen | None) -> None:
    """Ends the sim's processes: `just`, its shells and the host's (Wine) processes."""
    if process is None or process.poll() is not None:
        return

    for sent, wait in ((signal.SIGTERM, 2.0), (signal.SIGKILL, None)):  # Wine waits for the KILL
        try:
            os.killpg(process.pid, sent)
            process.wait(timeout=wait)
            return
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            continue


def keep_whole_results() -> int:
    """The fights a stopped sim finished: a result cut off as it was written is dropped."""
    whole = 0

    for path in HOST_RESULTS.glob("result-*.json"):
        try:
            json.loads(path.read_text())
            whole += 1
        except (json.JSONDecodeError, UnicodeDecodeError):
            path.unlink()

    return whole


def settings_json(slots: tuple[SlotAsk, ...]) -> list[dict]:
    return [
        {
            "hero_id": slot.champion_id,
            "sequences": [
                {
                    "starters": list(wave.openers),
                    "priorities": {str(k): v for k, v in wave.priorities.items()},
                }
                for wave in slot.waves
            ],
        }
        for slot in slots
    ]
