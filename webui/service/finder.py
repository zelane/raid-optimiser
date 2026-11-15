"""
finder.py - the champion finder: the account's champions whose name holds the text, of a
rarity and a faction and at least so many stars, in the game's default order. The pages that
open it decide what a pick does (the champion's optimiser, a team slot).

- `FINDER_LIMIT`: the most it lists
- `FinderPick`, `FinderView`: a champion as it lists them, and the list
- `find_champions`: what the finder asks for
- `account_factions`: the factions its filter offers
"""

from dataclasses import dataclass

from optimiser.account import Account, faction_name
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
    factions: tuple[str, ...]
    grades: tuple[int, ...]


def find_champions(account: Account, query: FinderQuery) -> FinderView:
    """The matches; a faction the account has none of means any."""
    wanted = query.text.casefold()
    factions = account_factions(account)
    faction = query.faction if query.faction in factions else None
    matches = [
        c
        for c in account.champions.values()
        if wanted in c.name.casefold()
        and (query.rarity is None or c.rarity == query.rarity)
        and (faction is None or faction_name(c.faction) == faction)
        and c.grade >= query.min_grade
    ]
    matches.sort(key=game_order, reverse=True)
    picks = [FinderPick(champion_row(c), choice_label(c)) for c in matches[:FINDER_LIMIT]]
    return FinderView(query, picks, len(matches), RARITIES, factions, GRADES)


def account_factions(account: Account) -> tuple[str, ...]:
    """The factions the account has champions of, by display name."""
    return tuple(sorted({faction_name(c.faction) for c in account.champions.values()}))
