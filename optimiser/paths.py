"""
paths.py - where the project keeps its data: the latest capture, the game's tables, the
schema they're decoded with, and the store. Everything that isn't code is under `data/`
(gitignored); the schema is tracked.

- `ROOT`, `DATA`, `CAPTURES`, `GAME`, `SCHEMA`, `STORE`, `POTENTIALS`: the paths
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CAPTURES = DATA / "captures" / "latest"
GAME = DATA / "game"  # the game's tables, from update-static.sh
SCHEMA = ROOT / "schema" / "schema.json"
STORE = DATA / "state" / "optimiser.sqlite"
POTENTIALS = DATA / "cache" / "potentials.pickle"  # accessory scores, kept by piece state
