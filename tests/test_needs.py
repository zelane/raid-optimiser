"""
test_needs.py - counting debuff instances (`optimiser.teams.needs.instances`, and the search's
`holds`): each different debuff once, each champion's Poisons as many as one of its skills
places, and one for a Toxic set any champion may wear.

- `test_poisons_count_as_many_as_one_skill_places`: a lone Poisoner isn't enough any more
- `test_the_toxic_set_is_one_poison`: gear adds one
- `test_the_search_counts_alike`: `holds` agrees with `instances`
"""

from optimiser.teams.kits import Kit, Rating
from optimiser.teams.needs import Distinct, Requirement, instances
from optimiser.teams.search import check_of, holds, poisons_of
from optimiser.teams.tags import Side, Tag, Target

POISON = Tag(Side.DEBUFF, "ContinuousDamage")
WEAKEN = Tag(Side.DEBUFF, "IncreaseDamageTaken")
DEF_DOWN = Tag(Side.DEBUFF, "DecreaseDefence")
RATED = Rating(1.0, 1.0, 1.0, 1.0, "")
ANYONE = Target("the enemies")


def kit(*tags: Tag, poisons: int = 1) -> Kit:
    counts = {POISON: poisons} if poisons > 1 else {}
    return Kit(None, {tag: RATED for tag in tags}, counts)  # type: ignore[arg-type]


def test_poisons_count_as_many_as_one_skill_places() -> None:
    five = Distinct(Side.DEBUFF, 5, instances=True)
    poisoner = kit(POISON, poisons=3)

    assert instances(five, [poisoner], ANYONE) == 3
    assert instances(five, [poisoner, kit(WEAKEN, DEF_DOWN)], ANYONE) == 5
    assert instances(five, [kit(POISON), kit(POISON, WEAKEN)], ANYONE) == 3


def test_the_toxic_set_is_one_poison() -> None:
    four = Distinct(Side.DEBUFF, 4, instances=True, gear=("Toxic set", 0.5))
    assert instances(four, [kit(POISON, poisons=2), kit(WEAKEN)], ANYONE) == 4


def test_the_search_counts_alike() -> None:
    five = Distinct(Side.DEBUFF, 5, instances=True)
    team = [kit(POISON, poisons=3), kit(WEAKEN, DEF_DOWN)]
    check = check_of(Requirement(five, ANYONE), team)
    tags = frozenset().union(*(k.tags for k in team))
    placed = sum(poisons_of(k, check.stacking) for k in team)

    assert holds(check, tags, placed)
    assert not holds(check, team[0].tags, poisons_of(team[0], check.stacking))
