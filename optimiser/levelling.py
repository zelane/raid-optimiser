"""
levelling.py - levelling champions with brews: the XP each level takes by grade, and what a brew
gives (`data/game/levelling.json`, the game's). XP carries over from level to level, so a brew
may take a champion up several.

- `Levelling`, `load_levelling`: the tables
- `level_after`, `brews_to_level`: where so much XP takes a champion from level 1, and the brews
  a level takes
"""

import math
from dataclasses import dataclass
from pathlib import Path

import orjson


@dataclass(frozen=True)
class Levelling:
    """`xp`: grade ("Stars3") -> the XP from each level to the next, from level 1; a brew gives
    `brew` XP, `matching` on a champion of its own affinity."""

    xp: dict[str, tuple[int, ...]]
    brew: int
    matching: int

    def max_level(self, grade: str) -> int:
        return len(self.xp[grade]) + 1


def load_levelling(game: Path) -> Levelling:
    raw = orjson.loads((game / "levelling.json").read_bytes())
    return Levelling(
        xp={grade: tuple(steps) for grade, steps in raw["xp"].items()},
        brew=raw["brew"],
        matching=raw["matching"],
    )


def level_after(levelling: Levelling, grade: str, xp: int) -> int:
    level = 1

    for step in levelling.xp[grade]:
        if xp < step:
            break

        xp -= step
        level += 1

    return level


def brews_to_level(levelling: Levelling, grade: str, level: int, per_brew: int) -> int:
    return math.ceil(sum(levelling.xp[grade][: level - 1]) / per_brew)
