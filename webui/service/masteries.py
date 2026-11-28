"""
masteries.py - the masteries page: the 6★ champions without a mastery in a tree's last row
(Helmsmasher's, Warmaster's), split into those holding the scrolls to reach it and those still to
farm for, with each kind of scroll they've had (held and spent) against what reaching it takes.

Reaching the last row takes a mastery in each row below the furthest they've reached, in one
tree: each row's price (the same for every mastery in it) from there down. What they've spent
counts on both sides, so a champion with two masteries in row 5 needs 750 Divine, not 550.

- `SCROLLS`: the scroll kinds, best first: the game's `MasteryPointType` and the name shown
- `ScrollCount`, `ShortOfTop`, `MasteriesPage`: the views
- `masteries_page`: what the page shows
- `short_of_top`, `still_to_unlock`, `spent`, `furthest_row`: its pieces
"""

from collections import Counter
from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.tables import MasteryType
from webui.service.champions import game_order
from webui.service.views import ChampionRow, champion_row

TOP_GRADE = 6  # the stars a champion needs for a last-row mastery
SCROLLS = (("Gold", "Divine"), ("Silver", "Advanced"), ("Bronze", "Basic"))


@dataclass(frozen=True)
class ScrollCount:
    """One kind of scroll: `have`, held and spent; `need`, spent and what's left to reach the
    last row; `short`, how many more to farm (0 when what they hold covers it)."""

    kind: str  # "Divine", "Advanced", "Basic"
    have: int
    need: int
    short: int


@dataclass(frozen=True)
class ShortOfTop:
    """`row`: the furthest row they have a mastery in, 0 for none; `count`: how many they
    have; `scrolls`: best first, kinds they neither have nor need left out."""

    champion: ChampionRow
    row: int
    count: int
    scrolls: list[ScrollCount]


@dataclass(frozen=True)
class MasteriesPage:
    last_row: int
    top_grade: int  # how many 6★ champions there are
    ready: list[ShortOfTop]  # holding enough to reach the last row, in the champion list's order
    farming: list[ShortOfTop]  # the fewest Divine to farm first, then Advanced, then Basic


def masteries_page(account: Account) -> MasteriesPage:
    types = account.tables.mastery_types
    last_row = max(mastery.row for mastery in types.values())
    top = [champion for champion in account.champions.values() if champion.grade == TOP_GRADE]
    short = [
        short_of_top(champion, types, last_row)
        for champion in sorted(top, key=game_order, reverse=True)
        if furthest_row(champion, types) < last_row
    ]

    def to_farm(item: ShortOfTop) -> tuple[int, ...]:
        return tuple(count.short for count in item.scrolls)

    return MasteriesPage(
        last_row=last_row,
        top_grade=len(top),
        ready=[item for item in short if not any(to_farm(item))],
        farming=sorted((item for item in short if any(to_farm(item))), key=to_farm),
    )


def short_of_top(champion: Champion, types: dict[int, MasteryType], last_row: int) -> ShortOfTop:
    row = furthest_row(champion, types)
    used = spent(champion, types)
    left = still_to_unlock(row, types, last_row)
    scrolls = []

    for kind, name in SCROLLS:
        held = champion.scrolls.get(kind, 0)
        have, need = held + used[kind], used[kind] + left[kind]

        if have or need:
            scrolls.append(ScrollCount(name, have, need, max(0, left[kind] - held)))

    return ShortOfTop(champion_row(champion), row, len(champion.masteries), scrolls)


def still_to_unlock(row: int, types: dict[int, MasteryType], last_row: int) -> Counter[str]:
    """The scrolls a mastery in each row from under `row` to the last costs."""
    prices = {mastery.row: mastery.price for mastery in types.values()}
    left: Counter[str] = Counter()

    for below in range(row + 1, last_row + 1):
        left.update(prices[below])

    return left


def spent(champion: Champion, types: dict[int, MasteryType]) -> Counter[str]:
    used: Counter[str] = Counter()

    for mastery in champion.masteries:
        if mastery in types:
            used.update(types[mastery].price)

    return used


def furthest_row(champion: Champion, types: dict[int, MasteryType]) -> int:
    return max((types[m].row for m in champion.masteries if m in types), default=0)
