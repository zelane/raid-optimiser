"""
test_relics.py - a relic a team slot's champion wears (`optimiser.teams.gear`): its skill level
from its level, its effects at that level, and what an echo (Sporeburst Rod) adds.

- `test_skill_level_follows_the_relic_level`: the game's table, highest step reached
- `test_only_the_level_s_tier_counts`: effects for other levels, and echoes, are left out
- `test_an_echo_adds_to_what_the_champion_places`: a Poisoner's count goes up by its chance
"""

from optimiser.tables import Placement, Skill
from optimiser.teams.gear import Gear, RelicSource, at_level, echoes_of, wear
from optimiser.teams.kits import Kit, Rating
from optimiser.teams.tags import Side, Tag

LEVELS = ((0, 1), (6, 2), (9, 3), (12, 4), (15, 5), (18, 6))
ROD = RelicSource(70, "Sporeburst Rod", (1,), {}, LEVELS)
POISON = Tag(Side.DEBUFF, "ContinuousDamage")


def placed(level: int, chance: float, echo: str | None = None) -> Placement:
    status = "ContinuousDamage5p"
    return Placement(
        "ApplyDebuff", status, 2, chance, "RelationTarget", None, False, 1, level, echo
    )


SKILL = Skill(
    id=1,
    name="rod",
    group="Passive",
    aoe=False,
    hits=(),
    book_damage=(),
    scaling=(),
    debuffs=frozenset(),
    buffs=frozenset(),
    effect_kinds=frozenset(),
    target_hp_damage=False,
    cooldown=0,
    placements=(
        placed(3, 0.2, "ContinuousDamage5p"),
        placed(4, 0.25, "ContinuousDamage5p"),
        placed(4, 0.5),
    ),
    books=(),
)


def test_skill_level_follows_the_relic_level() -> None:
    assert [ROD.skill_level(level) for level in (0, 5, 6, 11, 12, 18)] == [1, 1, 2, 3, 4, 6]


def test_only_the_level_s_tier_counts() -> None:
    assert [p.chance for p in at_level(SKILL, 4).placements] == [0.5]
    assert echoes_of(at_level(SKILL, 4, echoes=True)) == {POISON: 0.25}
    assert echoes_of(at_level(SKILL, 3, echoes=True)) == {POISON: 0.2}


RATED = Rating(1.0, 1.0, 1.0, 1.0, "")
ECHO = Gear("worn:1", "Sporeburst Rod", "relic", None, {}, {}, {POISON: 0.25})


def test_an_echo_adds_to_what_the_champion_places() -> None:
    poisoner = Kit(None, {POISON: RATED}, {POISON: 2})  # type: ignore[arg-type]
    assert wear(poisoner, (ECHO,)).counts[POISON] == 2.5

    other = Kit(None, {Tag(Side.DEBUFF, "Stun"): RATED})  # type: ignore[arg-type]
    assert POISON not in wear(other, (ECHO,)).counts  # no Poison of its own to echo
