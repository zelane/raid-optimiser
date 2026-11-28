"""
paths.py - where the project keeps its data: the account's snapshot, the game's tables, the
schemas they're decoded with, and the store. Everything that isn't code is under `data/`
(gitignored); the schema is tracked.

- `ROOT`, `DATA`, `SNAPSHOT`, `EVENTS`, `GAME`, `SCHEMA`, `EVENTS_SCHEMA`, `STORE`,
  `WATCH_LOG`, `POTENTIALS`, `HOST_RESULTS`, `LAST_SIM`, `SIM_TEAM`: the paths
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAPSHOT = DATA / "captures" / "snapshot.json"  # the account, from just read (or just watch)
EVENTS = DATA / "captures" / "events.json"  # its events, read apart: they change more often
GAME = DATA / "game"  # the game's tables, from just static
SCHEMA = ROOT / "schema" / "schema.json"
EVENTS_SCHEMA = ROOT / "schema" / "events.json"  # the snapshot's events, the game's JSON
STORE = DATA / "state" / "optimiser.sqlite"
WATCH_LOG = DATA / "cache" / "watch.log"  # what just watch, started from the web UI, says
POTENTIALS = DATA / "cache" / "potentials.pickle"  # accessory scores, kept by piece state
HOST_RESULTS = DATA / "cache" / "host" / "results"  # the battle host's last fights (just fight)
LAST_SIM = DATA / "cache" / "host" / "last-sim.json"  # the web UI's last sim, summed up
SIM_TEAM = DATA / "cache" / "host" / "sim-team.json"  # the web UI's sim's skill settings
