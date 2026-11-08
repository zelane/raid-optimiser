"""
store.py - what the user sets that the capture doesn't hold, kept in SQLite: champion locks.

A lock (1-5, 5 the strongest) keeps a champion's gear out of solves that only allow gear from
champions locked below some level. Unlocked champions have no row, and count as 0.

- `LOCK_LEVELS`, `Locks`: what a lock is
- `SCHEMA`: the table they're kept in
- `read_locks`, `write_lock`: reading and writing them
- `connect`: what they share
"""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

LOCK_LEVELS = range(1, 6)

type Locks = Mapping[int, int]  # champion id -> lock level; unlocked champions are absent

SCHEMA = """
CREATE TABLE IF NOT EXISTS champion_locks (
    champion_id INTEGER PRIMARY KEY,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5)
)
"""


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


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """One transaction, committed if the block finishes; the file is created if need be."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)

    try:
        with db:
            db.execute(SCHEMA)
            yield db
    finally:
        db.close()
