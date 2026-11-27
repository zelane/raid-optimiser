"""
summons.py - what opening shards earns in an event scoring summons (Champion Chase): each shard
type's odds (the game's, `data/game/shards.json`, or a running summon boost's, from the reader's
events file), the event's points by rarity and affinity, and how many shards of a type reaching
a score takes.

Opening is simulated from no mercy built up: the game keeps no count of the account's (the
server does), so an account part-way to a mercy does better than this says. Mercy: past
`mercy_after` shards without a rarity, each shard has `mercy_step` more chance of it, taken
from the shard's commonest rarity, until it comes. Shard types with no mercy (Mystery) are
worked out, not simulated: each shard the same, the count is the points over the mean, spread
as a sum of many.

- `DropRule`, `ShardType`, `Boost`, `Summons`, `Summoning`: odds, shard types, boosts, what the
  account holds, and both together
- `load_shard_types`, `load_summons`, `parse_summons`: from the game's tables and the reader
- `odds_now`, `summon_points`, `champion_points`: a shard's odds at a moment, what each rarity
  earns from it, and what one champion earns
- `Reach`, `shards_to_reach`, `points_per_shard`: how many shards a score takes, and the mean
- `simulate`, `reach`, `worked_out`, `draw_rarity`, `chances`: their steps
- `parse_rules`: what the loaders share
"""

import math
import random
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import orjson

from optimiser.events import Rule, rule_points

SUMMON = "Hero_Summon"  # the event action a shard's champion scores by
TRIALS = 400
LIKELY = 0.9  # the share of trials the "likely" count covers
LONG_RUN = 20_000  # shards opened to measure the mean points per shard
MAX_SHARDS = 5_000  # a simulated trial gives up past this many
SEED = 7  # so the page shows the same counts each time it's drawn


@dataclass(frozen=True)
class DropRule:
    rarity: str
    chance: float
    mercy_step: float | None
    mercy_after: int | None


@dataclass(frozen=True)
class ShardType:
    """`id` the game's ("Legendary" for a Sacred Shard), `name` as it's shown; `elements`
    the affinities it summons."""

    id: str
    name: str
    elements: tuple[str, ...]
    rules: tuple[DropRule, ...]


@dataclass(frozen=True)
class Boost:
    """A summon event standing in its own odds for a shard type's, between `start` and `end`."""

    event: str
    shard: str
    start: datetime
    end: datetime
    rules: tuple[DropRule, ...]


@dataclass(frozen=True)
class Summons:
    held: dict[str, int]  # shard type id -> how many the account holds
    boosts: tuple[Boost, ...]


@dataclass(frozen=True)
class Summoning:
    """What opening shards needs besides the event: the shard types, the account's summons."""

    shard_types: tuple[ShardType, ...]
    summons: Summons


def load_shard_types(game: Path) -> tuple[ShardType, ...]:
    return tuple(
        ShardType(raw["id"], raw["name"], tuple(raw["elements"]), parse_rules(raw["rules"]))
        for raw in orjson.loads((game / "shards.json").read_bytes())
    )


def load_summons(events: Path) -> Summons | None:
    """The reader's summons, in its events file (None without one, or if it read none)."""
    raw = orjson.loads(events.read_bytes()) if events.exists() else None
    return parse_summons(raw["summons"]) if raw and raw.get("summons") else None


def parse_summons(raw: dict) -> Summons:
    return Summons(
        held={held["shard"]: held["count"] for held in raw["held"]},
        boosts=tuple(
            Boost(
                event=boost["event"],
                shard=boost["shard"],
                start=datetime.fromtimestamp(boost["from"], UTC),
                end=datetime.fromtimestamp(boost["to"], UTC),
                rules=parse_rules(boost["rules"]),
            )
            for boost in raw["boosts"]
        ),
    )


def parse_rules(raw: list[dict]) -> tuple[DropRule, ...]:
    return tuple(
        DropRule(rule["rarity"], rule["chance"], rule["mercy_step"], rule["mercy_after"])
        for rule in raw
    )


def odds_now(
    shard: ShardType, boosts: tuple[Boost, ...], now: datetime
) -> tuple[tuple[DropRule, ...], Boost | None]:
    """The shard's odds now: a running boost's, else its own; and the boost."""
    running = next(
        (b for b in boosts if b.shard == shard.id and b.start <= now < b.end and b.rules), None
    )
    return (running.rules if running else shard.rules), running


def summon_points(rules: tuple[Rule, ...], shard: ShardType) -> dict[str, float]:
    """Rarity -> what a champion of it from this shard earns: the event's summon rule for each
    affinity the shard summons, averaged over them (none: 0)."""
    rarities = {
        str(c.value)
        for rule in rules
        if rule.action == SUMMON
        for c in rule.conditions
        if c.field == "Rarity"
    }
    elements = shard.elements or ("",)
    return {
        rarity: sum(champion_points(rules, rarity, e) for e in elements) / len(elements)
        for rarity in rarities
    }


def champion_points(rules: tuple[Rule, ...], rarity: str, element: str) -> int:
    """What summoning a champion of this rarity and affinity earns (no rule for it: 0)."""
    return rule_points(rules, SUMMON, {"Rarity": rarity, "Elements": element})


@dataclass(frozen=True)
class Reach:
    """Shards of one type a score takes: `typical` half the time, `likely` nine times in ten;
    None when they don't reach it (its champions earn nothing)."""

    typical: int
    likely: int


def shards_to_reach(
    rules: tuple[DropRule, ...], points: dict[str, float], targets: tuple[int, ...]
) -> tuple[Reach | None, ...]:
    """For each target (points still to earn), the shards of this type it takes."""
    by_rarity = tuple(sorted(points.items()))

    if points_per_shard(rules, by_rarity) <= 0:
        return tuple(None for _ in targets)

    if not any(rule.mercy_step for rule in rules):
        return tuple(worked_out(rules, points, target) for target in targets)

    return simulate(rules, by_rarity, targets)


@lru_cache(maxsize=256)
def points_per_shard(rules: tuple[DropRule, ...], points: tuple[tuple[str, float], ...]) -> float:
    """The mean a shard earns over a long run, mercy included."""
    by_rarity = dict(points)
    generator = random.Random(SEED)
    since = {rule.rarity: 0 for rule in rules}
    total = sum(by_rarity.get(draw_rarity(rules, since, generator), 0) for _ in range(LONG_RUN))
    return total / LONG_RUN


@lru_cache(maxsize=256)
def simulate(
    rules: tuple[DropRule, ...], points: tuple[tuple[str, float], ...], targets: tuple[int, ...]
) -> tuple[Reach | None, ...]:
    """`TRIALS` runs of opening shards until the highest target, each noting the shard that
    passed each target (lowest first)."""
    by_rarity = dict(points)
    generator = random.Random(SEED)
    counts: list[list[int]] = [[] for _ in targets]
    lowest_first = sorted(range(len(targets)), key=lambda index: targets[index])

    for _ in range(TRIALS):
        since = {rule.rarity: 0 for rule in rules}
        ahead = iter(lowest_first)
        target = next(ahead, None)
        earned, opened = 0.0, 0

        while target is not None and opened < MAX_SHARDS:
            earned += by_rarity.get(draw_rarity(rules, since, generator), 0)
            opened += 1

            while target is not None and earned >= targets[target]:
                counts[target].append(opened)
                target = next(ahead, None)

    return tuple(reach(found) for found in counts)


def reach(found: list[int]) -> Reach | None:
    if len(found) < TRIALS * LIKELY:
        return None

    ordered = sorted(found)
    return Reach(int(statistics.median(ordered)), ordered[math.ceil(LIKELY * len(ordered)) - 1])


def worked_out(rules: tuple[DropRule, ...], points: dict[str, float], target: int) -> Reach:
    """Without mercy each shard is the same draw: the count is about the target over the mean,
    and spread as a sum of that many draws (normal: 1.28 sd for nine in ten)."""
    mean = sum(rule.chance * points.get(rule.rarity, 0) for rule in rules)
    square = sum(rule.chance * points.get(rule.rarity, 0) ** 2 for rule in rules)
    spread = math.sqrt(max(square - mean**2, 0))
    typical = target / mean
    likely = typical + 1.28 * spread * math.sqrt(typical) / mean
    return Reach(math.ceil(typical), math.ceil(likely))


def draw_rarity(
    rules: tuple[DropRule, ...], since: dict[str, int], generator: random.Random
) -> str:
    """Opens a shard: the rarity it gives, moving `since` (shards since each rarity came) on."""
    roll = generator.random()
    drawn = rules[-1].rarity

    for rarity, chance in chances(rules, since):
        if roll < chance:
            drawn = rarity
            break

        roll -= chance

    for rarity in since:
        since[rarity] = 0 if rarity == drawn else since[rarity] + 1

    return drawn


def chances(rules: tuple[DropRule, ...], since: dict[str, int]) -> list[tuple[str, float]]:
    """Each rarity's chance now: its own plus its mercy, the extra taken from the commonest."""
    extra = {
        rule.rarity: rule.mercy_step * (since[rule.rarity] - rule.mercy_after + 1)
        for rule in rules
        if rule.mercy_step and rule.mercy_after is not None
        if since[rule.rarity] >= rule.mercy_after
    }
    commonest = max(rules, key=lambda rule: rule.chance).rarity
    given = sum(extra.values())

    return [
        (
            (
                rule.rarity,
                max(rule.chance - given, 0) if rule.rarity == commonest else rule.chance,
            )
            if rule.rarity not in extra
            else (rule.rarity, min(rule.chance + extra[rule.rarity], 1))
        )
        for rule in rules
    ]
