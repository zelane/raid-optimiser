"""
finder.py - the champion finder: the account's champions whose name holds the text, of a
rarity and at least so many stars, in the game's default order. The pages that open it decide
what a pick does (the champion's optimiser, a Chimera slot).

- `FINDER_LIMIT`: the most it lists
- `FinderPick`, `FinderView`: a champion as it lists them, and the list
- `find_champions`: what the finder asks for
"""

from dataclasses import dataclass

from optimiser.account import Account
from webui.forms.finder import GRADES, RARITIES, FinderQuery
from webui.service.champions import game_order
from webui.service.views import ChampionRow, champion_row, choice_label

FINDER_LIMIT = 60


@dataclass(frozen=True)
class FinderPick:
    """`choice`: the champion as the Chimera slot picker names them ("Name, 6★ L60 #id")."""

    champion: ChampionRow
    choice: str


@dataclass(frozen=True)
class FinderView:
    query: FinderQuery
    picks: list[FinderPick]  # the first `FINDER_LIMIT`
    found: int
    rarities: tuple[str, ...]
    grades: tuple[int, ...]


def find_champions(account: Account, query: FinderQuery) -> FinderView:
    wanted = query.text.casefold()
    matches = [
        c
        for c in account.champions.values()
        if wanted in c.name.casefold()
        and (query.rarity is None or c.rarity == query.rarity)
        and c.grade >= query.min_grade
    ]
    matches.sort(key=game_order, reverse=True)
    picks = [FinderPick(champion_row(c), choice_label(c)) for c in matches[:FINDER_LIMIT]]
    return FinderView(query, picks, len(matches), RARITIES, GRADES)
