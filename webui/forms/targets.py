"""
targets.py - the target picker's query into a `TargetQuery`.

Fields: `zone`, `group`, `difficulty`, `stage` (a stage id), `enemy` ("<wave>-<slot>"): each
level's pick, any of them absent; `changed`: the field the user just changed (htmx's
`HX-Trigger-Name`), whose lower levels go back to their defaults; `target`
("<stage>:<wave>:<slot>"), a saved pick that overrides the rest. Anything unknown falls back
to a default rather than failing: the picker always shows something.

- `LEVELS`, `SAVED`: the picker's levels, top first, and a saved pick's shape
- `SavedTarget`, `TargetQuery`: the parsed query
- `parse_target_query` (`parse_saved`): the boundary
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

LEVELS = ("zone", "group", "difficulty", "stage", "enemy")
SAVED = re.compile(r"(\d+):(\d+):(\d+)")


@dataclass(frozen=True)
class SavedTarget:
    stage: int
    enemy: str  # "<wave>-<slot>"


@dataclass(frozen=True)
class TargetQuery:
    zone: str | None = None
    group: str | None = None
    difficulty: str | None = None
    stage: str | None = None
    enemy: str | None = None
    target: SavedTarget | None = None


def parse_target_query(query: Mapping[str, str], changed: str | None) -> TargetQuery:
    if (saved := parse_saved(query.get("target", ""))) is not None:
        return TargetQuery(enemy=saved.enemy, target=saved)

    kept = LEVELS[: LEVELS.index(changed) + 1] if changed in LEVELS else LEVELS

    def pick(level: str) -> str | None:
        return (query.get(level) or None) if level in kept else None

    return TargetQuery(
        zone=pick("zone"),
        group=pick("group"),
        difficulty=pick("difficulty"),
        stage=pick("stage"),
        enemy=pick("enemy"),
    )


def parse_saved(text: str) -> SavedTarget | None:
    if not (match := SAVED.fullmatch(text.strip())):
        return None

    stage, wave, slot = match.groups()
    return SavedTarget(int(stage), f"{wave}-{slot}")
