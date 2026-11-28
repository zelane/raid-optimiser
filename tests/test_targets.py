"""
test_targets.py - what the target picker and the damage it feeds depend on: which stage
modifiers reach an enemy, the sets' damage bonus, the picker's query and its group names.

- `test_boss_only_modifiers_replace_the_general_ones`: a stage's general and boss-only copies
  of a modifier never both apply
- `test_damage_bonus_stacks_per_set_up_to_its_cap`: Zeal per set to its cap, Fury once
- `test_changed_level_resets_the_ones_under_it`, `test_saved_target_wins`: the picker's query
- `test_shared_region_names_get_what_tells_them_apart`: Iron Twins, Hydra, Grim Forest
- `test_team_list_by_region_then_area`: the saved-team list a stage's team screen offers
"""

from dataclasses import dataclass

from optimiser.damage import bonus_from_sets
from optimiser.enemies import (
    EnemyForm,
    EnemyType,
    Modifier,
    Placement,
    Stage,
    modifier_applies,
    team_list,
)
from optimiser.tables import DamageBonus, FixedSet, Stat
from webui.forms.targets import SavedTarget, parse_target_query
from webui.service.targets import group_labels

ZEAL = FixedSet(1, "Zeal", 2, (), (), (DamageBonus(100042, 0.12, per_set=True, cap=0.36),))
FURY = FixedSet(2, "Fury", 4, (), (), (DamageBonus(100001, 0.10, per_set=False, cap=None),))


@dataclass(frozen=True)
class Worn:
    set_id: int


def enemy(boss_kind: str | None) -> EnemyType:
    return EnemyType(1, "Hellrazor", (EnemyForm("Force", (), {}),), boss_kind, unkillable=False)


def test_boss_only_modifiers_replace_the_general_ones() -> None:
    general = Modifier(3, Stat.DEF, -0.5, absolute=False, boss_only=False)
    boss_only = Modifier(3, Stat.DEF, -0.5, absolute=False, boss_only=True)
    in_wave_3 = Placement(1, wave=3, slot=1, grade=6, level=280, boss=True, modifiers=())

    assert not modifier_applies(general, in_wave_3, enemy("Dragon"))
    assert modifier_applies(boss_only, in_wave_3, enemy("Dragon"))
    assert modifier_applies(general, in_wave_3, enemy(None))
    assert not modifier_applies(boss_only, in_wave_3, enemy(None))


def test_damage_bonus_stacks_per_set_up_to_its_cap() -> None:
    sets = {1: ZEAL, 2: FURY}

    def bonus(*set_ids: int) -> float:
        return round(bonus_from_sets([Worn(s) for s in set_ids], sets), 6)  # type: ignore[misc]

    assert bonus(1, 1) == 0.12
    assert bonus(1, 1, 1) == 0.12  # a third piece isn't a second set
    assert bonus(*[1] * 6) == 0.36
    assert bonus(*[1] * 8) == 0.36  # capped
    assert bonus(*[2] * 8) == 0.10  # Fury's doesn't stack
    assert bonus(1, 1, 2, 2, 2, 2) == 0.22


def test_changed_level_resets_the_ones_under_it() -> None:
    picks = {"zone": "Fractions", "group": "Fraction_Orcs", "difficulty": "Hard", "stage": "5"}
    query = parse_target_query(picks, changed="group")

    assert (query.zone, query.group, query.difficulty, query.stage) == (
        "Fractions",
        "Fraction_Orcs",
        None,
        None,
    )
    assert parse_target_query(picks, changed=None).stage == "5"


def test_saved_target_wins() -> None:
    query = parse_target_query({"zone": "Dungeon", "target": "14032201:1:3"}, changed=None)

    assert query.target == SavedTarget(14032201, "1-3")
    assert query.zone is None
    assert query.enemy == "1-3"


def test_shared_region_names_get_what_tells_them_apart() -> None:
    labels = group_labels(
        [
            ("VoidDoubleAscendDungeon", "Iron Twins Fortress"),
            ("ForceDoubleAscendDungeon", "Iron Twins Fortress"),
            ("AllianceHydraSeason1", "Hydra"),
            ("AllianceHydraSeason2", "Hydra"),
            ("FoggyForestEasyZone", "Grim Forest"),
            ("FoggyForestExtraHardZone", "Grim Forest"),
            ("DragonsLair", "Dragon's Lair"),
        ]
    )

    assert labels == {
        "VoidDoubleAscendDungeon": "Iron Twins Fortress: Void",
        "ForceDoubleAscendDungeon": "Iron Twins Fortress: Force",
        "AllianceHydraSeason1": "Hydra: Season 1",
        "AllianceHydraSeason2": "Hydra: Season 2",
        "FoggyForestEasyZone": "Grim Forest: Easy",
        "FoggyForestExtraHardZone": "Grim Forest: Extra Hard",
        "DragonsLair": "Dragon's Lair",
    }


def test_team_list_by_region_then_area() -> None:
    def stage(area: str | None, region: str | None) -> Stage:
        return Stage(1, area, region, None, 5, (), (), (), ())

    assert team_list(stage("Dungeon", "IceGolemCave")) == "ArtifactDungeons"
    assert team_list(stage("Dungeon", "SpiritKeep")) == "PotionKeeps"
    assert team_list(stage("Dungeon", "MinotaurCave")) == "ArtifactAscendAndMasteries"
    assert team_list(stage("Fractions", "Fraction_Orcs")) == "Fractions"
    assert team_list(stage("Chimera", "ChimeraRotation2")) == "Chimera"
    assert team_list(stage("CursedCity", "CursedCityDistrict1")) == "GeneralPve"
    assert team_list(stage(None, None)) == "GeneralPve"
