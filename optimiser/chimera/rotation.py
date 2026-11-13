"""
rotation.py - which trials give which rewards this raid, as the game decides it
(`ChimeraExtensions.GetChimeraChallengeRewardWithOffset` and `GetPrizeOffset`): a tier's
reward lists, in the game's order (Ram, Lion, Snake × Wing, Tail, Paw), shift over the trials by
the raid's prize offset; a trial gets the list `(its own index + offset) % 9`, at its level.
With offset 0 the Mythical relic materials are on Tail's Hard trials, so their column cycles
Tail → Wing → Paw as the offset grows.

- `MYTHICAL`: the reward that makes a column worth a team
- `prize_offset`: the offset in force at a time (the previous raid's until the raid opens)
- `trial_reward`: what a trial gives
- `mythical_column`: the column whose trials give Mythical materials this raid
"""

from datetime import datetime, timedelta

from optimiser.account import ChimeraRaid
from optimiser.chimera.trials import PARTS, PLAN_DIFFICULTY
from optimiser.enemies import Chimera, ChimeraTier, RaidTiming, Reward

MYTHICAL = "RelicCraftMaterial_Chimera_Mythical"


def prize_offset(raid: ChimeraRaid, timing: RaidTiming, now: datetime) -> int:
    """The raid's offset once it's open (`activity_hours` before the next raid starts, 24 h
    after its own start); before that, the previous raid's."""
    opens = raid.start + timedelta(hours=timing.hours_between_raids - timing.activity_hours)

    if now >= opens:
        return raid.prize_offset

    return raid.prize_offset - 1 if raid.prize_offset > 0 else timing.max_prize_offset


def trial_reward(
    tier: ChimeraTier, form: str, part: str, level: str, offset: int
) -> tuple[Reward, ...]:
    lists = tier.rewards
    own = next(i for i, rewards in enumerate(lists) if (rewards.form, rewards.part) == (form, part))
    return lists[(own + offset) % len(lists)].by_level.get(level, ())


def mythical_column(chimera: Chimera, raid: ChimeraRaid, now: datetime) -> str | None:
    """The column most of whose trials give Mythical materials at the planned difficulty."""
    tier = next(t for t in chimera.tiers if t.difficulty == PLAN_DIFFICULTY)
    offset = prize_offset(raid, chimera.timing, now)
    counts = {
        part: sum(
            any(r.item == MYTHICAL for r in trial_reward(tier, t.form, part, t.level, offset))
            for t in tier.trials
            if t.part == part
        )
        for part in PARTS
    }
    best = max(PARTS, key=lambda part: counts[part])
    return best if counts[best] else None
