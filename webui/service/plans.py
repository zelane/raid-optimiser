"""
plans.py - what reaching an event's milestones takes, by what it scores: shards opened
(`summons`: Champion Chase), champions brewed (`training`: Champion Training), dungeon runs
(`fights`: Turn Attack, Ice Golem's), pieces upgraded (`upgrades`: Gear Enhancement). The one
place a card gets its plans; the page draws each by its `kind`, under the milestone picked.

- `EventPlan`: any of them
- `event_plans`: an event's
"""

from datetime import datetime

from optimiser.event_tables import PlanTables
from optimiser.events import GameEvent, Milestone
from webui.service.fights import FightPlan, fight_plan
from webui.service.summons import SummonPlan, summon_plan
from webui.service.training import BrewPlan, brew_plan
from webui.service.upgrades import UpgradePlan, upgrade_plan

type EventPlan = SummonPlan | BrewPlan | FightPlan | UpgradePlan


def event_plans(
    event: GameEvent,
    points: int,
    milestones: tuple[Milestone, ...],
    tables: PlanTables,
    now: datetime,
) -> tuple[EventPlan, ...]:
    """`points`: the account's in it; `milestones`: its bracket's."""
    summons = tables.summoning and summon_plan(event, points, milestones, tables.summoning, now)
    plans = (
        summons,
        brew_plan(event, tables.levelling),
        fight_plan(event, tables.loot),
        upgrade_plan(event),
    )
    return tuple(plan for plan in plans if plan)
