"""
targets.py - the target picker's query into a `TargetQuery`.

Fields: `zone`, `group`, `difficulty`, `stage` (a stage id), `wave` (1 first), `enemy`
("<wave>-<slot>"): each level's pick, any of them absent; `changed`: the field the user just
changed (the picker sends it), whose lower levels go back to their defaults; `target`
("<stage>:<wave>:<slot>"), a saved pick that overrides the rest. Anything unknown falls back
to a default rather than failing: the picker always shows something.

- `LEVELS`, `SAVED`: the picker's levels, top first, and a saved pick's shape
- `SavedTarget`, `TargetQuery`: the parsed query
- `parse_target_query` (`parse_saved`), `saved_query`: the boundary
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

LEVELS = ("zone", "group", "difficulty", "stage", "wave", "enemy")
SAVED = re.compile(r"(\d+)(?::(\d+):(\d+))?")


@dataclass(frozen=True)
class SavedTarget:
    stage: int
    enemy: str | None  # "<wave>-<slot>"; None: the stage's default

    @property
    def wave(self) -> int | None:
        return int(self.enemy.split("-")[0]) if self.enemy else None


@dataclass(frozen=True)
class TargetQuery:
    zone: str | None = None
    group: str | None = None
    difficulty: str | None = None
    stage: str | None = None
    wave: int | None = None
    enemy: str | None = None
    target: SavedTarget | None = None


def parse_target_query(query: Mapping[str, str], changed: str | None) -> TargetQuery:
    if (saved := parse_saved(query.get("target", ""))) is not None:
        return saved_query(saved)

    kept = LEVELS[: LEVELS.index(changed) + 1] if changed in LEVELS else LEVELS

    def pick(level: str) -> str | None:
        return (query.get(level) or None) if level in kept else None

    return TargetQuery(
        zone=pick("zone"),
        group=pick("group"),
        difficulty=pick("difficulty"),
        stage=pick("stage"),
        wave=int(text) if (text := pick("wave") or "").isdigit() else None,
        enemy=pick("enemy"),
    )


def parse_saved(text: str) -> SavedTarget | None:
    if not (match := SAVED.fullmatch(text.strip())):
        return None

    stage, wave, slot = match.groups()
    return SavedTarget(int(stage), f"{wave}-{slot}" if wave else None)


def saved_query(saved: SavedTarget | None) -> TargetQuery:
    """The picker at a saved pick (None: its defaults)."""
    if saved is None:
        return TargetQuery()

    return TargetQuery(wave=saved.wave, enemy=saved.enemy, target=saved)
