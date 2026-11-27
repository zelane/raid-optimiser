"""
current.py - the state the pages read: the account (reparsed only when `just read` writes a
new snapshot), the game's enemies, the champion locks and the reserve rules.

- `current_account`, `snapshot_mtime`, `load_for`: the account, reloaded when a new snapshot lands
- `current_events`, `events_mtime`, `events_for`: the events on in the game, reloaded when the
  reader writes them (more often than the account, under `just watch`)
- `current_summons`, `summons_for`, `current_shard_types`, `shard_types_for`: the shards held
  and summon boosts (in the events file), and the game's shard odds
- `current_levelling`, `levelling_for`: the XP champions' levels take, and brews give
- `current_loot`, `loot_for`: the gear dungeon stages drop
- `current_summoning`, `current_plan_tables`: those together, as the event plans read them
- `current_enemies`, `enemies_for`: the game's enemies, reloaded after a game update
- `current_effect_sources`, `effect_sources_for`: the sets' and relics' skills, likewise
- `current_locks`: champion locks, kept in the store
- `current_reserve_rules`: what reserves gear, kept in the store
"""

from functools import lru_cache

from optimiser.account import Account, Locks, load_account
from optimiser.enemies import Enemies, load_enemies
from optimiser.event_tables import PlanTables
from optimiser.events import Events, load_events
from optimiser.levelling import Levelling, load_levelling
from optimiser.loot import Loot, load_loot
from optimiser.paths import EVENTS, EVENTS_SCHEMA, GAME, SCHEMA, SNAPSHOT, STORE
from optimiser.reserve import Rule
from optimiser.settings import read_reserve_rules
from optimiser.store import read_locks
from optimiser.summons import ShardType, Summoning, Summons, load_shard_types, load_summons
from optimiser.teams.gear import RelicSource, SetSource, load_effect_sources


def current_enemies() -> Enemies:
    """The game's enemies; reparsed only after a game update rewrites them."""
    return enemies_for(GAME.joinpath("enemies.json").stat().st_mtime_ns)


@lru_cache(maxsize=1)
def enemies_for(enemies_mtime: int) -> Enemies:  # the mtime is only the cache key
    return load_enemies(GAME)


def current_effect_sources() -> tuple[tuple[SetSource, ...], tuple[RelicSource, ...]]:
    """The sets' and relics' skills; reparsed only after a game update rewrites them."""
    return effect_sources_for(GAME.joinpath("effect_sources.json").stat().st_mtime_ns)


@lru_cache(maxsize=1)
def effect_sources_for(mtime: int) -> tuple[tuple[SetSource, ...], tuple[RelicSource, ...]]:
    return load_effect_sources(GAME)  # the mtime is only the cache key


def current_account() -> Account:
    """The latest snapshot; reparsed only when it changes."""
    return load_for(snapshot_mtime())


def snapshot_mtime() -> int:
    return SNAPSHOT.stat().st_mtime_ns


@lru_cache(maxsize=1)
def load_for(snapshot_mtime: int) -> Account:  # the mtime is only the cache key
    return load_account(SNAPSHOT, GAME, SCHEMA)


def current_events() -> Events | None:
    """The reader's events (None if it found none); reparsed only when they change."""
    return events_for(events_mtime())


def events_mtime() -> int:
    return EVENTS.stat().st_mtime_ns if EVENTS.exists() else 0


@lru_cache(maxsize=1)
def events_for(events_mtime: int) -> Events | None:  # the mtime is only the cache key
    return load_events(EVENTS, EVENTS_SCHEMA, GAME)


def current_summons() -> Summons | None:
    return summons_for(events_mtime())


@lru_cache(maxsize=1)
def summons_for(events_mtime: int) -> Summons | None:  # the mtime is only the cache key
    return load_summons(EVENTS)


def current_shard_types() -> tuple[ShardType, ...]:
    return shard_types_for(GAME.joinpath("shards.json").stat().st_mtime_ns)


@lru_cache(maxsize=1)
def shard_types_for(mtime: int) -> tuple[ShardType, ...]:  # the mtime is only the cache key
    return load_shard_types(GAME)


def current_levelling() -> Levelling:
    return levelling_for(GAME.joinpath("levelling.json").stat().st_mtime_ns)


@lru_cache(maxsize=1)
def levelling_for(mtime: int) -> Levelling:  # the mtime is only the cache key
    return load_levelling(GAME)


def current_loot() -> Loot:
    return loot_for(GAME.joinpath("loot.json").stat().st_mtime_ns)


@lru_cache(maxsize=1)
def loot_for(mtime: int) -> Loot:  # the mtime is only the cache key
    return load_loot(GAME)


def current_summoning() -> Summoning | None:
    """The shards held and their odds; None when the reader found no summons."""
    summons = current_summons()
    return None if summons is None else Summoning(current_shard_types(), summons)


def current_plan_tables() -> PlanTables:
    return PlanTables(current_summoning(), current_levelling(), current_loot())


def current_locks() -> Locks:
    return read_locks(STORE)


def current_reserve_rules() -> tuple[Rule, ...]:
    return read_reserve_rules(STORE)
