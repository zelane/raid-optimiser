"""
test_summons.py - what opening shards earns in an event scoring summons.

- `test_mercy_takes_from_the_commonest`: past its count a rarity gains, the commonest gives
- `test_points_by_the_shards_affinity`: a Void shard by the Void column, the rest by theirs
- `test_without_mercy_its_worked_out`: the count is the target over the mean, and spread
- `test_simulated_counts_agree_with_the_odds`: boosted Sacred shards, as worked by hand
- `test_a_running_boost_stands_in`: a boost's odds while it runs, the shard's own after
"""

from datetime import UTC, datetime, timedelta

from optimiser.events import Condition, Rule
from optimiser.summons import (
    Boost,
    DropRule,
    ShardType,
    chances,
    odds_now,
    shards_to_reach,
    summon_points,
)

ANCIENT = (
    DropRule("Rare", 0.915, None, None),
    DropRule("Epic", 0.08, 0.02, 20),
    DropRule("Legendary", 0.005, 0.05, 200),
)
SACRED_BOOSTED = (DropRule("Epic", 0.88, None, None), DropRule("Legendary", 0.12, 0.02, 12))
NOT_VOID = ("Force", "Magic", "Spirit")
CHASE = tuple(
    Rule("Hero_Summon", (Condition("Hero", "Rarity", rarity), Condition("Hero", "Elements", e)), p)
    for rarity, e, p in [
        ("Rare", NOT_VOID, 10),
        ("Rare", ("Void",), 50),
        ("Epic", NOT_VOID, 250),
        ("Epic", ("Void",), 350),
        ("Legendary", NOT_VOID, 500),
        ("Legendary", ("Void",), 650),
    ]
)
NOW = datetime(2026, 11, 28, tzinfo=UTC)


def test_mercy_takes_from_the_commonest() -> None:
    fresh = dict(chances(ANCIENT, {"Rare": 0, "Epic": 0, "Legendary": 0}))
    assert fresh == {"Rare": 0.915, "Epic": 0.08, "Legendary": 0.005}

    due = dict(chances(ANCIENT, {"Rare": 0, "Epic": 0, "Legendary": 201}))
    assert round(due["Legendary"], 3) == 0.105  # two shards past 200: 0.5 % + 2 × 5 %
    assert round(due["Rare"], 3) == 0.815 and due["Epic"] == 0.08


def test_points_by_the_shards_affinity() -> None:
    void = ShardType("Void", "Void Shard", ("Void",), ANCIENT)
    ancient = ShardType("Ancient", "Ancient Shard", ("Magic", "Force", "Spirit"), ANCIENT)

    assert summon_points(CHASE, void) == {"Rare": 50, "Epic": 350, "Legendary": 650}
    assert summon_points(CHASE, ancient) == {"Rare": 10, "Epic": 250, "Legendary": 500}


def test_without_mercy_its_worked_out() -> None:
    mystery = (DropRule("Common", 0.5, None, None), DropRule("Uncommon", 0.5, None, None))
    (reach,) = shards_to_reach(mystery, {"Common": 1, "Uncommon": 3}, (200,))

    assert reach is not None and reach.typical == 100  # 2 points a shard
    assert reach.typical < reach.likely < 110


def test_simulated_counts_agree_with_the_odds() -> None:
    points = {"Epic": 250, "Legendary": 500}
    (reach,) = shards_to_reach(SACRED_BOOSTED, points, (2_800,))

    # 250 a shard and 250 more for a legendary: 2,800 takes shards + legendaries ≥ 12. Ten
    # shards do it 34 % of the time (2+ legendaries at 12 %), eleven 75 % (1+), twelve always
    # (mercy, past 12, never comes into it)
    assert reach is not None and (reach.typical, reach.likely) == (11, 12)


def test_a_running_boost_stands_in() -> None:
    sacred = ShardType("Legendary", "Sacred Shard", NOT_VOID, (DropRule("Epic", 1.0, None, None),))
    boost = Boost("X2 Sacred", "Legendary", NOW, NOW + timedelta(days=1), SACRED_BOOSTED)

    assert odds_now(sacred, (boost,), NOW + timedelta(hours=1)) == (SACRED_BOOSTED, boost)
    assert odds_now(sacred, (boost,), NOW + timedelta(days=2)) == (sacred.rules, None)
