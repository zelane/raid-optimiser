"""
reader.py - syncing the account: runs `just read` (the memory reader, in the game's prefix;
the justfile knows the paths), which rewrites the snapshot the pages reload from, or keeps
`just watch` running, which rewrites it (and the events) as the account changes.

The watcher runs in a session of its own, so it outlives the web server's reloads, and
whether it's running is read off the processes (`/proc`), not kept: `just watch` while it
starts, then the reader it runs. Stopping it stops both (the reader outlives its launcher in
the game's container).

- `TIMEOUT`: how long a read may take (it takes about 2.5 s, plus starting the prefix's tools)
- `sync`: read the account now (one read at a time)
- `STARTING`, `STOPPING`, `watching`, `start_watch`, `stop_watch`: the watcher
- `synced_ago`, `age_text`: how old the snapshot is, as the nav shows it, and any file
- `watch_processes`, `is_watcher`: its pieces
"""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from optimiser.paths import ROOT, SNAPSHOT, WATCH_LOG
from webui.result import Err, Result

TIMEOUT = 60.0
LINES = 3  # of the reader's output, kept as the reason a read failed

STARTING = 3.0  # seconds a started watcher has to fail in before it counts as started
STOPPING = 5.0  # seconds a stopped one has to be gone in
READER = "raid-reader.exe"

_reading = threading.Lock()


def sync() -> Result[None]:
    if not _reading.acquire(blocking=False):
        return Err("a sync is already running")

    try:
        done = subprocess.run(
            ["just", "read"], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT
        )
    except FileNotFoundError:
        return Err("`just` isn't on the web server's PATH")
    except subprocess.TimeoutExpired:
        return Err(f"the reader took over {TIMEOUT:g} s")
    finally:
        _reading.release()

    if done.returncode != 0:
        lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
        return Err(" / ".join(lines[-LINES:]) or f"`just read` exited {done.returncode}")

    return None


def watching() -> bool:
    return bool(watch_processes())


def start_watch() -> Result[None]:
    """`just watch`, in its own session, its output in `paths.WATCH_LOG`: refused if one is
    already running, failed if it exits at once (the game not running)."""
    if watching():
        return Err("already watching")

    WATCH_LOG.parent.mkdir(parents=True, exist_ok=True)

    with WATCH_LOG.open("w") as log:
        try:
            watcher = subprocess.Popen(
                ["just", "watch"],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError:
            return Err("`just` isn't on the web server's PATH")

    try:
        watcher.wait(timeout=STARTING)
    except subprocess.TimeoutExpired:
        return None

    lines = [line for line in WATCH_LOG.read_text().splitlines() if line.strip()]
    return Err(" / ".join(lines[-LINES:]) or f"`just watch` exited {watcher.returncode}")


def stop_watch() -> Result[None]:
    """Stops the watcher, and waits (up to `STOPPING`) for it to be gone, so the page that
    asked reloads without it."""
    if not (pids := watch_processes()):
        return Err("not watching")

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # gone already: stopping one stops the others

    deadline = time.monotonic() + STOPPING

    while watching():
        if time.monotonic() > deadline:
            return Err(f"still running {STOPPING:g} s after being stopped")

        time.sleep(0.1)

    return None


def watch_processes() -> list[int]:
    """`just watch` (and the recipe it runs) and the watching reader, by pid."""
    found = []

    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue

        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue  # gone, or not ours to read

        if is_watcher([arg.decode(errors="replace") for arg in args if arg]):
            found.append(int(entry.name))

    return found


def is_watcher(args: list[str]) -> bool:
    match args:
        case [program, "watch"] | [program, "reader-run", "--watch"] if (
            Path(program).name == "just"
        ):
            return True

        case [program, "--watch", *_] if program.endswith(READER):
            return True

    return False


def synced_ago() -> str:
    return age_text(SNAPSHOT)


def age_text(path: Path) -> str:
    """ "never" without the file; else minutes, hours or days."""
    if not path.exists():
        return "never"

    minutes = int(time.time() - path.stat().st_mtime) // 60

    if minutes < 1:
        return "just now"

    if minutes < 60:
        return f"{minutes} min ago"

    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"

    return f"{minutes // (24 * 60)} days ago"
