"""
fights.py - the runs to make for an event scoring dungeon runs: by their turns (Turn Attack
tournaments: what a run earns at each turn count, `TurnPoints.points`, the page asking the turns
the account's team usually takes) or by the gear they drop (Ice Golem's: a run's average, from
the stage's drop odds, `optimiser.loot`), per stage, so the page can say how many runs reaching
a milestone takes.

- `STAGE_FIELDS`, `MAX_TURNS`
- `FightStage`, `FightPlan`: the views
- `fight_plan`: an event's plan, if it scores runs
- `turn_stages`, `loot_stages`: its stages, by how it scores them
- `stage_label`, `stages_text`, `loot_label`: a stage as the page shows it
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.events import GameEvent, Rule, TurnPoints
from optimiser.loot import DUNGEON_REWARD, Loot, Place, run_points

STAGE_FIELDS = ("Number", "MinNumber", "MaxNumber")  # a dungeon rule's stages
MAX_TURNS = 200  # the most turns the page offers a run's points for
NORMAL = "Normal"


@dataclass(frozen=True)
class FightStage:
    """A stage (or run of them) and what a run in it earns: by its turns, `points[n - 1]` for
    n turns up to `MAX_TURNS`; else one average, `points[0]`."""

    label: str
    points: tuple[float, ...]


@dataclass(frozen=True)
class FightPlan:
    stages: tuple[FightStage, ...]  # the hardest first
    by_turns: bool


def fight_plan(event: GameEvent, loot: Loot) -> FightPlan | None:
    if stages := turn_stages(event.rules):
        return FightPlan(stages, by_turns=True)

    if stages := loot_stages(event.rules, loot):
        return FightPlan(stages, by_turns=False)

    return None


def turn_stages(rules: tuple[Rule, ...]) -> tuple[FightStage, ...]:
    scored = [rule for rule in rules if isinstance(rule.points, TurnPoints)]
    difficulties = {c.value for rule in scored for c in rule.conditions if c.field == "Difficulty"}
    return tuple(
        FightStage(
            stage_label(rule, len(difficulties) > 1),
            tuple(float(rule.points.points(turns)) for turns in range(1, MAX_TURNS + 1)),
        )
        for rule in reversed(scored)
        if isinstance(rule.points, TurnPoints)
    )


def loot_stages(rules: tuple[Rule, ...], loot: Loot) -> tuple[FightStage, ...]:
    """Each stage of the regions the event's gear rules name that earns something, the hardest
    difficulty first, then the highest stage."""
    regions = {
        c.value
        for rule in rules
        if rule.action == DUNGEON_REWARD
        for c in rule.conditions
        if c.field == "RegionTypeId"
    }
    places = [
        (Place(str(region), difficulty, number), stage)
        for region in sorted(regions)
        for difficulty, stages in reversed(loot.get(str(region), {}).items())
        for number, stage in reversed(list(enumerate(stages, start=1)))
        if stage
    ]
    earning = [(place, run_points(rules, place, stage)) for place, stage in places]
    return tuple(
        FightStage(loot_label(place), (round(points, 1),)) for place, points in earning if points
    )


def stage_label(rule: Rule, with_difficulty: bool) -> str:
    """Its stages ("Stages 21–24"), and its difficulty when the event's stages differ in it."""
    stages = stages_text({c.field: c.value for c in rule.conditions if c.field in STAGE_FIELDS})
    difficulty = next((c.value for c in rule.conditions if c.field == "Difficulty"), None)
    return f"{stages} ({difficulty})" if with_difficulty and difficulty else stages


def stages_text(stages: Mapping[str, object]) -> str:
    match stages:
        case {"Number": number}:
            return f"Stage {number}"

        case {"MinNumber": low, "MaxNumber": high}:
            return f"Stages {low}–{high}"

    return "Any stage"


def loot_label(place: Place) -> str:
    return (
        f"Stage {place.number}"
        if place.difficulty == NORMAL
        else f"{place.difficulty} {place.number}"
    )
