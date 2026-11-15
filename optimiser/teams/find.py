"""
find.py - the team finder's entry points, for any `Goals`: what the champions in the slots
meet on their own (`check_slots`), and every way to fill the open slots from a pool of
champions (`find_teams`: every smallest team meeting them all within `SEARCH_BUDGET`, best
scored first; failing that, the few meeting the most).

- `Found`: what a search found
- `check_slots`, `find_teams`: the workflows
- `slot_kits`: the slots' champions as kits, with what they could wear or are assumed to bring
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.teams.cover import Lineup, lineup_of, ranking
from optimiser.teams.gear import Loadout, equip
from optimiser.teams.kits import Kit, kit_of
from optimiser.teams.needs import Goals
from optimiser.teams.search import PARTIAL_OPTIONS, SEARCH_BUDGET, every_team, partial_teams


@dataclass(frozen=True)
class Found:
    """The slots as the user filled them (`lineup`), and the teams found keeping them, best
    first: `found` in all (`complete`: no more exist), `options` the first of them as
    lineups. `partial`: none meets every objective, so these meet the most they can.
    `candidates`: the champions the search could add."""

    lineup: Lineup
    options: tuple[Lineup, ...]
    found: int
    complete: bool
    partial: bool
    candidates: int


def check_slots(
    account: Account, loadout: Loadout, slots: tuple[Champion | None, ...], goals: Goals
) -> Lineup:
    """What the champions in the slots meet on their own."""
    return lineup_of(slot_kits(account, loadout, slots), set(), goals)


def find_teams(
    account: Account,
    loadout: Loadout,
    slots: tuple[Champion | None, ...],
    goals: Goals,
    pool: list[Champion],
    shown: int,
) -> Found:
    """The slots' champions kept, the open slots filled from `pool` (one copy of each
    champion, as `kits.candidates` gives): every smallest team meeting every objective and
    extra (within `SEARCH_BUDGET`), the best scored first (`ranking`); the first `shown` of
    them as lineups. If none meets them all, a few meeting the most."""
    # 1. Who's in the slots, and who could join them, each with what they could wear or are
    #    assumed to bring.
    chosen = slot_kits(account, loadout, slots)
    pinned = [kit for kit in chosen if kit]
    taken = {kit.champion.type_id // 10 for kit in pinned}
    others = [
        equip(kit_of(account, champion), loadout)
        for champion in pool
        if champion.type_id // 10 not in taken
    ]

    # 2. Every team meeting them all, or failing that the few meeting the most.
    found, complete = every_team(pinned, others, goals, SEARCH_BUDGET)
    partial = not found
    if partial:
        found = partial_teams(pinned, others, goals, PARTIAL_OPTIONS)
    else:
        found.sort(key=lambda added: ranking(pinned + added, goals))

    # 3. The first of them as lineups, each one's newcomers in the open slots in order.
    teams = []

    for added in found[:shown]:
        newcomers = iter(added)
        filled = [kit if kit else next(newcomers, None) for kit in chosen]
        teams.append(lineup_of(filled, {id(kit) for kit in added}, goals))

    return Found(
        lineup=lineup_of(chosen, set(), goals),
        options=tuple(teams),
        found=len(found),
        complete=complete,
        partial=partial,
        candidates=len(others),
    )


def slot_kits(
    account: Account, loadout: Loadout, slots: tuple[Champion | None, ...]
) -> list[Kit | None]:
    """The slots' champions' kits, with what they could wear or are assumed to bring."""
    return [equip(kit_of(account, c), loadout) if c else None for c in slots]
