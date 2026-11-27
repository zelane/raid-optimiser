"""
test_loot.py - what a dungeon run earns in an event scoring the gear it drops.

- `test_rank_and_rarity_add_up`: a piece earns its rank's points and its rarity's, at the odds
- `test_another_stage_earns_nothing`: a rule held to a region or stages counts only there
"""

from optimiser.events import Condition, Rule
from optimiser.loot import Place, StageLoot, run_points

GOLEM = Condition("Dungeon", "RegionTypeId", "IceGolemCave")
ICE_GOLEM = (
    Rule("Battle_DungeonReward", (Condition("Artifact", "Rank", "Five"), GOLEM), 15),
    Rule("Battle_DungeonReward", (Condition("Artifact", "Rank", "Six"), GOLEM), 20),
    Rule("Battle_DungeonReward", (Condition("Artifact", "Rarity", "Rare"), GOLEM), 1),
    Rule("Battle_DungeonReward", (Condition("Artifact", "Rarity", "Epic"), GOLEM), 2),
    Rule("Battle_DungeonReward", (Condition("Artifact", "Rarity", "Legendary"), GOLEM), 5),
)
STAGE_25 = StageLoot(
    0.995, {"Five": 0.68, "Six": 0.32}, {"Rare": 0.55, "Epic": 0.32, "Legendary": 0.13}
)


def test_rank_and_rarity_add_up() -> None:
    points = run_points(ICE_GOLEM, Place("IceGolemCave", "Normal", 25), STAGE_25)

    # ranks 0.68 × 15 + 0.32 × 20 = 16.6, rarities 0.55 + 0.64 + 0.65 = 1.84, a piece 99.5 %
    assert round(points, 2) == round(0.995 * 18.44, 2)


def test_another_stage_earns_nothing() -> None:
    assert run_points(ICE_GOLEM, Place("DragonsLair", "Normal", 25), STAGE_25) == 0

    early = (Rule("Battle_DungeonReward", (Condition("Dungeon", "MaxNumber", 10),), 3),)
    assert run_points(early, Place("IceGolemCave", "Normal", 25), STAGE_25) == 0
    assert run_points(early, Place("IceGolemCave", "Normal", 9), STAGE_25) == 0.995 * 3
