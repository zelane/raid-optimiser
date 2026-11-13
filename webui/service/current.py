"""
current.py - the state the pages read: the latest capture (reparsed only when the proxy
writes a new one), the game's enemies, the champion locks, and the roster's faction types.

- `current_account`, `capture_mtime`, `load_for`: the account, reloaded when a new capture lands
- `current_enemies`, `enemies_for`: the game's enemies, reloaded after a game update
- `current_effect_sources`, `effect_sources_for`: the sets' and relics' skills, likewise
- `current_locks`: champion locks, kept in the store
- `roster_types`: the capture's faction types (cached)
"""

from functools import lru_cache

from optimiser.accessories.roles import ChampionType
from optimiser.accessories.scaling import faction_types
from optimiser.account import Account, Locks, load_account
from optimiser.chimera.gear import RelicSource, SetSource, load_effect_sources
from optimiser.enemies import Enemies, load_enemies
from optimiser.paths import CAPTURES, GAME, SCHEMA, STORE
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
    """The latest capture; reparsed only when it changes (the proxy rewrites it often)."""
    return load_for(capture_mtime())


def capture_mtime() -> int:
    return CAPTURES.joinpath("champions.json").stat().st_mtime_ns


@lru_cache(maxsize=1)
def load_for(capture_mtime: int) -> Account:  # the mtime is only the cache key
    return load_account(CAPTURES, GAME, SCHEMA)


def current_locks() -> Locks:
    return read_locks(STORE)


@lru_cache(maxsize=1)
def roster_types(capture_mtime: int) -> tuple[ChampionType, ...]:
    """The faction types of the capture's roster; the mtime is only the cache key."""
    return faction_types(load_for(capture_mtime))
