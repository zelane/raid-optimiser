"""
paths.py - where the project keeps its data: the account's snapshot, the game's tables, the
schema they're decoded with, and the store. Everything that isn't code is under `data/`
(gitignored); the schema is tracked.

- `ROOT`, `DATA`, `SNAPSHOT`, `GAME`, `SCHEMA`, `STORE`, `POTENTIALS`: the paths
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAPSHOT = DATA / "captures" / "snapshot.json"  # the account, from just read
GAME = DATA / "game"  # the game's tables, from just static
SCHEMA = ROOT / "schema" / "schema.json"
STORE = DATA / "state" / "optimiser.sqlite"
POTENTIALS = DATA / "cache" / "potentials.pickle"  # accessory scores, kept by piece state
