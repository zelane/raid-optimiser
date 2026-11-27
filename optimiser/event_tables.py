"""
event_tables.py - what the events' plans read besides the events, together: the shards the
account holds and their odds (`optimiser.summons`), the XP champions' levels take
(`optimiser.levelling`) and the gear dungeon stages drop (`optimiser.loot`).

- `PlanTables`
"""

from dataclasses import dataclass

from optimiser.levelling import Levelling
from optimiser.loot import Loot
from optimiser.summons import Summoning


@dataclass(frozen=True)
class PlanTables:
    summoning: Summoning | None  # None when the reader found no summons
    levelling: Levelling
    loot: Loot
