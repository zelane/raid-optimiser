"""
summons.py - the shards to open for an event scoring summons (Champion Chase): how many shards
of each type reaching a milestone takes (`optimiser.summons`: at today's odds, boosts included,
from no mercy built up), beside how many the account holds and what those would earn.

The page picks the milestone (the next not reached, unless a row is clicked) and may count
champions it expects besides (`MANUAL`, by kind: fused, or summoned since the last read; marked
by rarity colour, Void by a triangle), whose points come off what's still to earn; each change
asks `/events/{id}/shards` again (`shard_rows`), so only the first target's counts come with
the page.

- `MANUAL`: the champion kinds counted by hand: key, rarity, void, label
- `ShardReach`, `ShardRow`, `ManualKind`, `SummonPlan`: the views
- `summon_plan`: an event's plan, if it scores summons and has a milestone left
- `shard_rows`: the shards a shortfall takes, by type
- `shard_row`, `boost_text`: its pieces
"""

from dataclasses import dataclass
from datetime import datetime

from optimiser.events import GameEvent, Milestone
from optimiser.summons import (
    SUMMON,
    Boost,
    ShardType,
    Summoning,
    Summons,
    champion_points,
    odds_now,
    points_per_shard,
    shards_to_reach,
    summon_points,
)
from webui.service.views import span_text

MANUAL = (
    ("m", "Mythical", False, "Mythical"),
    ("vl", "Legendary", True, "Void legendary"),
    ("l", "Legendary", False, "Legendary"),
    ("ve", "Epic", True, "Void epic"),
    ("e", "Epic", False, "Epic"),
)
VOID = "Void"
NOT_VOID = "Magic"  # any affinity but Void: the events' tables give them one column


@dataclass(frozen=True)
class ShardReach:
    """Shards a target takes: `typical` half the time, `likely` nine times in ten."""

    typical: int
    likely: int


@dataclass(frozen=True)
class ShardRow:
    """One shard type: `per_shard` the mean points one earns; `held_earns` what those held
    would; `reach` the shards the shortfall takes, None if they can't (its champions earn
    nothing); `boost` how long a running summon boost has left."""

    name: str
    held: int
    per_shard: float
    held_earns: int
    boost: str | None
    reach: ShardReach | None


@dataclass(frozen=True)
class ManualKind:
    """A kind of champion counted by hand ("vl": a Void legendary), and what one earns; the
    page marks it by its rarity's colour, a triangle for Void."""

    key: str
    label: str
    rarity: str  # the game's ("Legendary")
    void: bool
    points: int


@dataclass(frozen=True)
class SummonPlan:
    """`target`: the milestone picked first (the next not reached); `rows` the shards its
    shortfall takes; `shards_url` where the page asks for another shortfall's
    (`?short=<points>`)."""

    target: int
    rows: tuple[ShardRow, ...]
    kinds: tuple[ManualKind, ...]
    shards_url: str


def summon_plan(
    event: GameEvent,
    points: int,
    milestones: tuple[Milestone, ...],
    summoning: Summoning,
    now: datetime,
) -> SummonPlan | None:
    if not any(rule.action == SUMMON for rule in event.rules):
        return None

    if (target := next((m.points for m in milestones if m.points > points), None)) is None:
        return None

    return SummonPlan(
        target=target,
        rows=shard_rows(event, summoning, target - points, now),
        kinds=tuple(
            ManualKind(
                key,
                label,
                rarity,
                void,
                champion_points(event.rules, rarity, VOID if void else NOT_VOID),
            )
            for key, rarity, void, label in MANUAL
        ),
        shards_url=f"/events/{event.id}/shards",
    )


def shard_rows(
    event: GameEvent, summoning: Summoning, short: int, now: datetime
) -> tuple[ShardRow, ...]:
    """Each shard type whose champions earn points, and what `short` points take of it."""
    rows = (
        shard_row(event, shard, summoning.summons, short, now) for shard in summoning.shard_types
    )
    return tuple(row for row in rows if row.per_shard > 0)


def shard_row(
    event: GameEvent, shard: ShardType, summons: Summons, short: int, now: datetime
) -> ShardRow:
    rules, boost = odds_now(shard, summons.boosts, now)
    points = summon_points(event.rules, shard)
    per_shard = points_per_shard(rules, tuple(sorted(points.items())))
    held = summons.held.get(shard.id, 0)
    (reach,) = shards_to_reach(rules, points, (max(short, 1),))

    return ShardRow(
        name=shard.name,
        held=held,
        per_shard=round(per_shard, 1),
        held_earns=round(held * per_shard),
        boost=boost_text(boost, now),
        reach=ShardReach(reach.typical, reach.likely) if reach else None,
    )


def boost_text(boost: Boost | None, now: datetime) -> str | None:
    return f"boosted, {span_text(boost.end - now)} left" if boost else None
