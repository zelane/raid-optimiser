"""
reader.py - syncing the account: runs `just read` (the memory reader, in the game's prefix;
the justfile knows the paths), which rewrites the snapshot the pages reload from.

- `TIMEOUT`: how long a read may take (it takes about 2.5 s, plus starting the prefix's tools)
- `sync`: read the account now (one read at a time)
- `synced_ago`: how old the snapshot is, as the nav shows it
"""

import subprocess
import threading
import time

from optimiser.paths import ROOT, SNAPSHOT
from webui.result import Err, Result

TIMEOUT = 60.0
LINES = 3  # of the reader's output, kept as the reason a read failed

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


def synced_ago() -> str:
    """ "never" without a snapshot; else minutes, hours or days."""
    if not SNAPSHOT.exists():
        return "never"

    minutes = int(time.time() - SNAPSHOT.stat().st_mtime) // 60

    if minutes < 1:
        return "just now"

    if minutes < 60:
        return f"{minutes} min ago"

    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"

    return f"{minutes // (24 * 60)} days ago"
