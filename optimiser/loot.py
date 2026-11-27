"""
loot.py - the gear dungeon stages drop (`data/game/loot.json`, the game's odds), and what a run
earns on average in an event scoring it by rank and rarity (Ice Golem's tournament): each rule a
piece matches adds its points, rank and rarity drawn apart.

- `DUNGEON_REWARD`: the action events score dropped gear by
- `Place`, `StageLoot`, `Loot`, `load_loot`: the odds, by region, difficulty and stage
- `run_points`, `rule_chance`: what a run earns, and how often a piece meets a rule
"""

from dataclasses import dataclass
from pathlib import Path

import orjson

from optimiser.events import Condition, Rule, holds

DUNGEON_REWARD = "Battle_DungeonReward"


@dataclass(frozen=True)
class Place:
    region: str  # the game's ("IceGolemCave")
    difficulty: str  # "Normal" for a region with one
    number: int  # from 1

    def facts(self) -> dict[str, object]:
        """Where a run was, as the events' dungeon conditions name it."""
        return {"RegionTypeId": self.region, "Difficulty": self.difficulty, "Number": self.number}


@dataclass(frozen=True)
class StageLoot:
    """`pieces` a run drops on average; their odds by rank ("Six") and by rarity."""

    pieces: float
    ranks: dict[str, float]
    rarities: dict[str, float]


type Loot = dict[str, dict[str, tuple[StageLoot | None, ...]]]  # region -> difficulty -> stages


def load_loot(game: Path) -> Loot:
    raw = orjson.loads((game / "loot.json").read_bytes())
    return {
        region: {
            difficulty: tuple(StageLoot(**stage) if stage else None for stage in stages)
            for difficulty, stages in by_difficulty.items()
        }
        for region, by_difficulty in raw.items()
    }


def run_points(rules: tuple[Rule, ...], place: Place, loot: StageLoot) -> float:
    return loot.pieces * sum(
        rule.points * rule_chance(rule.conditions, place, loot)
        for rule in rules
        if rule.action == DUNGEON_REWARD and isinstance(rule.points, int)
    )


def rule_chance(conditions: tuple[Condition, ...], place: Place, loot: StageLoot) -> float:
    """How often a piece from this stage meets the rule: its rank's and rarity's odds, the rest
    held to where the run was (`events.holds`): 0 for another stage, or for a condition on the
    piece the odds don't give (its set, its slot)."""
    facts = place.facts()
    chance = 1.0

    for condition in conditions:
        match condition:
            case Condition("Artifact", "Rank", str(rank)):
                chance *= loot.ranks.get(rank, 0)

            case Condition("Artifact", "Rarity", str(rarity)):
                chance *= loot.rarities.get(rarity, 0)

            case _ if not holds(condition, facts):
                return 0

    return chance
