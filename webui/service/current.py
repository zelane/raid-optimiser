"""
current.py - the state the pages read: the account (reparsed only when `just read` writes a
new snapshot), the game's enemies, the champion locks, the reserve rules, and the roster's
faction types.

- `current_account`, `snapshot_mtime`, `load_for`: the account, reloaded when a new snapshot lands
- `current_enemies`, `enemies_for`: the game's enemies, reloaded after a game update
- `current_effect_sources`, `effect_sources_for`: the sets' and relics' skills, likewise
- `current_locks`: champion locks, kept in the store
- `current_reserve_rules`: what reserves gear, kept in the store
- `roster_types`: the roster's faction types (cached)
"""

from functools import lru_cache

from optimiser.accessories.roles import ChampionType
from optimiser.accessories.scaling import faction_types
from optimiser.account import Account, Locks, load_account
from optimiser.chimera.gear import RelicSource, SetSource, load_effect_sources
from optimiser.enemies import Enemies, load_enemies
from optimiser.paths import GAME, SCHEMA, SNAPSHOT, STORE
from optimiser.reserve import Rule
from optimiser.settings import read_reserve_rules
from optimiser.store import read_locks


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


def current_locks() -> Locks:
    return read_locks(STORE)


def current_reserve_rules() -> tuple[Rule, ...]:
    return read_reserve_rules(STORE)


@lru_cache(maxsize=1)
def roster_types(snapshot_mtime: int) -> tuple[ChampionType, ...]:
    """The faction types of the account's roster; the mtime is only the cache key."""
    return faction_types(load_for(snapshot_mtime))
