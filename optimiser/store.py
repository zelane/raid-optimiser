"""
store.py - what the capture doesn't hold, kept in SQLite: champion locks, and each
champion's run history.

A lock (1-5, 5 the strongest) keeps a champion's gear out of solves that only allow gear from
champions locked below some level. Unlocked champions have no row, and count as 0.

A run is a solve as a front end asked and showed it: the form it was asked with and what it
found, both JSON the front end writes and reads (opaque here), with a summary for listings.

- `LOCK_LEVELS`, `Locks`: what a lock is
- `NewRun`, `RunEntry`, `Run`: a run to save, as listed, and in full
- `SCHEMA`: the tables
- `read_locks`, `write_lock`: locks
- `save_run`, `list_runs`, `read_run`, `latest_run`, `delete_run`: runs
- `connect`, `run_from_row`: what they share
"""

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOCK_LEVELS = range(1, 6)

type Locks = Mapping[int, int]  # champion id -> lock level; unlocked champions are absent


@dataclass(frozen=True)
class NewRun:
    champion_id: int
    summary: str  # what was asked, in a line
    note: str  # what came of it: "3 builds", "no build"
    form: dict[str, str]
    outcome: dict  # the front end's own JSON


@dataclass(frozen=True)
class RunEntry:
    id: int
    ran_at: datetime  # UTC
    summary: str
    note: str


@dataclass(frozen=True)
class Run:
    entry: RunEntry
    form: dict[str, str]
    outcome: dict


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS champion_locks (
        champion_id INTEGER PRIMARY KEY,
        level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5)
    )""",
    """CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY,
        champion_id INTEGER NOT NULL,
        ran_at TEXT NOT NULL,  -- ISO 8601, UTC
        summary TEXT NOT NULL,
        note TEXT NOT NULL,
        form TEXT NOT NULL,  -- JSON
        outcome TEXT NOT NULL  -- JSON
    )""",
    "CREATE INDEX IF NOT EXISTS runs_by_champion ON runs (champion_id, id)",
)
RUN_COLUMNS = "id, ran_at, summary, note, form, outcome"


def read_locks(path: Path) -> dict[int, int]:
    if not path.exists():
        return {}

    with connect(path) as db:
        return dict(db.execute("SELECT champion_id, level FROM champion_locks").fetchall())


def write_lock(path: Path, champion_id: int, level: int) -> None:
    """Locks the champion at `level`; 0 unlocks them."""
    with connect(path) as db:
        if level == 0:
            db.execute("DELETE FROM champion_locks WHERE champion_id = ?", (champion_id,))
            return

        db.execute(
            "INSERT INTO champion_locks (champion_id, level) VALUES (?, ?)"
            " ON CONFLICT (champion_id) DO UPDATE SET level = excluded.level",
            (champion_id, level),
        )


def save_run(path: Path, run: NewRun, ran_at: datetime) -> Run:
    form, outcome = json.dumps(run.form), json.dumps(run.outcome)

    with connect(path) as db:
        cursor = db.execute(
            "INSERT INTO runs (champion_id, ran_at, summary, note, form, outcome)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run.champion_id, ran_at.isoformat(), run.summary, run.note, form, outcome),
        )

    entry = RunEntry(cursor.lastrowid or 0, ran_at, run.summary, run.note)
    return Run(entry, run.form, run.outcome)


def list_runs(path: Path, champion_id: int, limit: int) -> list[RunEntry]:
    """Newest first."""
    if not path.exists():
        return []

    with connect(path) as db:
        rows = db.execute(
            "SELECT id, ran_at, summary, note FROM runs WHERE champion_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (champion_id, limit),
        ).fetchall()

    return [RunEntry(run_id, datetime.fromisoformat(at), *texts) for run_id, at, *texts in rows]


def read_run(path: Path, champion_id: int, run_id: int) -> Run | None:
    """None when the champion has no such run."""
    if not path.exists():
        return None

    with connect(path) as db:
        row = db.execute(
            f"SELECT {RUN_COLUMNS} FROM runs WHERE champion_id = ? AND id = ?",
            (champion_id, run_id),
        ).fetchone()

    return run_from_row(row) if row else None


def latest_run(path: Path, champion_id: int) -> Run | None:
    if not path.exists():
        return None

    with connect(path) as db:
        row = db.execute(
            f"SELECT {RUN_COLUMNS} FROM runs WHERE champion_id = ? ORDER BY id DESC LIMIT 1",
            (champion_id,),
        ).fetchone()

    return run_from_row(row) if row else None


def delete_run(path: Path, champion_id: int, run_id: int) -> None:
    with connect(path) as db:
        db.execute("DELETE FROM runs WHERE champion_id = ? AND id = ?", (champion_id, run_id))


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """One transaction, committed if the block finishes; the file is created if need be."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)

    try:
        with db:
            for statement in SCHEMA:
                db.execute(statement)

            yield db
    finally:
        db.close()


def run_from_row(row: tuple) -> Run:
    run_id, ran_at, summary, note, form, outcome = row
    entry = RunEntry(run_id, datetime.fromisoformat(ran_at), summary, note)
    return Run(entry, json.loads(form), json.loads(outcome))
