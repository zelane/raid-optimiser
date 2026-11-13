"""
store.py - what the snapshot doesn't hold, kept in SQLite: champion locks, the glyphs to
assume on gear, account-wide settings, and each champion's run history.

A lock (1-5, 5 the strongest) keeps a champion's gear out of solves that only allow gear from
champions locked below some level. Unlocked champions have no row, and count as 0.

Glyphs are account-wide: each glyph kind ("SPD", "HP%") with the grade to assume
("6-Legendary"), both as `optimiser.glyphs` names them (opaque here). Kinds not assumed
have no row.

Settings are named flags ("max_gear_level"), on when they have a row; `optimiser.assume`
names them.

Type weights are what `optimiser.accessories.roles` values a stat at for a champion type,
keyed by the type's and the stat's names (opaque here); weights left at their default have no
row. Reserve rules say what gear is kept for something else (`optimiser.reserve` names them;
opaque here), in the order they were added. Protected pieces are accessories the clean-up must
never drop. Numbers are named settings with a value ("target_free"); unset ones have no row.

`optimiser.settings` reads the flags, glyphs, weights and reserve rules back as the model's
types.

A run is a solve as a front end asked and showed it: the form it was asked with and what it
found, both JSON the front end writes and reads (opaque here), with a summary for listings.

- `NewRun`, `RunEntry`, `Run`: a run to save, as listed, and in full
- `SCHEMA`: the tables
- `read_locks`, `write_lock`: locks
- `read_glyphs`, `write_glyph`: glyphs
- `read_flags`, `write_flag`: settings
- `WeightKey`, `read_weights`, `write_weight`: champion type weights
- `read_reserve_rules`, `write_reserve_rule`: reserve rules
- `read_protected`, `write_protected`: protected accessories
- `read_number`, `write_number`: numeric settings
- `save_run`, `list_runs`, `read_run`, `latest_run`, `delete_run`: runs
- `write_member`, `connect`, `run_from_row`: what they share
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

type WeightKey = tuple[str, str]  # champion type, stat


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
    """CREATE TABLE IF NOT EXISTS glyphs (
        kind TEXT PRIMARY KEY,
        grade TEXT NOT NULL
    )""",
    "CREATE TABLE IF NOT EXISTS flags (name TEXT PRIMARY KEY)",
    "DROP TABLE IF EXISTS accessory_weights",  # per main stat: replaced by type weights
    """CREATE TABLE IF NOT EXISTS type_weights (
        type TEXT NOT NULL,
        stat TEXT NOT NULL,
        weight REAL NOT NULL,
        PRIMARY KEY (type, stat)
    )""",
    "CREATE TABLE IF NOT EXISTS reserve_rules (key TEXT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS protected_artifacts (artifact_id INTEGER PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS numbers (name TEXT PRIMARY KEY, value REAL NOT NULL)",
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


def read_glyphs(path: Path) -> dict[str, str]:
    """Glyph kind -> the grade assumed."""
    if not path.exists():
        return {}

    with connect(path) as db:
        return dict(db.execute("SELECT kind, grade FROM glyphs").fetchall())


def write_glyph(path: Path, kind: str, grade: str | None) -> None:
    """Assumes `grade` for the kind; None stops assuming one."""
    with connect(path) as db:
        if grade is None:
            db.execute("DELETE FROM glyphs WHERE kind = ?", (kind,))
            return

        db.execute(
            "INSERT INTO glyphs (kind, grade) VALUES (?, ?)"
            " ON CONFLICT (kind) DO UPDATE SET grade = excluded.grade",
            (kind, grade),
        )


def read_flags(path: Path) -> set[str]:
    """The flags that are on."""
    if not path.exists():
        return set()

    with connect(path) as db:
        return {name for (name,) in db.execute("SELECT name FROM flags").fetchall()}


def write_flag(path: Path, name: str, on: bool) -> None:
    write_member(path, "flags", "name", name, on)


def read_weights(path: Path) -> dict[WeightKey, float]:
    if not path.exists():
        return {}

    with connect(path) as db:
        rows = db.execute("SELECT type, stat, weight FROM type_weights").fetchall()

    return {(type_name, stat): weight for type_name, stat, weight in rows}


def write_weight(path: Path, key: WeightKey, weight: float) -> None:
    with connect(path) as db:
        db.execute(
            "INSERT INTO type_weights (type, stat, weight) VALUES (?, ?, ?)"
            " ON CONFLICT (type, stat) DO UPDATE SET weight = excluded.weight",
            (*key, weight),
        )


def read_reserve_rules(path: Path) -> list[str]:
    """Oldest first."""
    if not path.exists():
        return []

    with connect(path) as db:
        rows = db.execute("SELECT key FROM reserve_rules ORDER BY rowid").fetchall()

    return [key for (key,) in rows]


def write_reserve_rule(path: Path, key: str, on: bool) -> None:
    write_member(path, "reserve_rules", "key", key, on)


def read_protected(path: Path) -> set[int]:
    if not path.exists():
        return set()

    with connect(path) as db:
        rows = db.execute("SELECT artifact_id FROM protected_artifacts").fetchall()

    return {artifact_id for (artifact_id,) in rows}


def write_protected(path: Path, artifact_id: int, protected: bool) -> None:
    write_member(path, "protected_artifacts", "artifact_id", artifact_id, protected)


def read_number(path: Path, name: str) -> float | None:
    if not path.exists():
        return None

    with connect(path) as db:
        row = db.execute("SELECT value FROM numbers WHERE name = ?", (name,)).fetchone()

    return row[0] if row else None


def write_number(path: Path, name: str, value: float) -> None:
    with connect(path) as db:
        db.execute(
            "INSERT INTO numbers (name, value) VALUES (?, ?)"
            " ON CONFLICT (name) DO UPDATE SET value = excluded.value",
            (name, value),
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


def write_member(path: Path, table: str, column: str, value: str | int, on: bool) -> None:
    """Puts `value` in (or takes it out of) a table of one key column; `table` and `column`
    are this module's own names, never input."""
    with connect(path) as db:
        if on:
            db.execute(f"INSERT OR IGNORE INTO {table} ({column}) VALUES (?)", (value,))
        else:
            db.execute(f"DELETE FROM {table} WHERE {column} = ?", (value,))


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
