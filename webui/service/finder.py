"""
finder.py - the account's champions as the champion list and the finder (the picker dialog)
list them: whose name holds the text, of a rarity and a faction and at least so many stars,
in the game's default order, each with their lock. The list locks them; a page opening the
finder decides what a pick does (the champion's optimiser, a team slot).

- `FINDER_LIMIT`: the most it lists
- `ListedChampion`, `FinderView`: a champion as it lists them, and the list
- `find_champions`, `lock_champion`: what the pages ask for
- `account_factions`: the factions its filter offers
- `OnlyView`, `only_view`, `restriction_label`: a page's hold on the list (what its stage
  admits), as the dialog sends and shows it
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion, Locks, faction_label, faction_name
from optimiser.enemies import Restriction
from optimiser.paths import STORE
from optimiser.store import write_lock
from webui.forms.finder import GRADES, RARITIES, FinderQuery
from webui.service.champions import game_order
from webui.service.views import ChampionRow, Choice, champion_row, slot_value

FINDER_LIMIT = 200


@dataclass(frozen=True)
class ListedChampion:
    """`choice`: the champion as the team slots name them (`views.slot_value`); `lock`: their
    lock level (0: unlocked)."""

    champion: ChampionRow
    choice: str
    lock: int


@dataclass(frozen=True)
class FinderView:
    query: FinderQuery
    picks: list[ListedChampion]  # the first `FINDER_LIMIT`
    found: int
    rarities: tuple[str, ...]
    factions: tuple[Choice, ...]  # by display name ("DarkElves"), labelled as the game shows it
    grades: tuple[int, ...]


def find_champions(account: Account, locks: Locks, query: FinderQuery) -> FinderView:
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
        and (query.only is None or query.only.admits(c))
    ]
    matches.sort(key=game_order, reverse=True)
    picks = [listed(c, locks.get(c.id, 0)) for c in matches[:FINDER_LIMIT]]
    choices = tuple(Choice(name, faction_label(name)) for name in factions)
    return FinderView(query, picks, len(matches), RARITIES, choices, GRADES)


def lock_champion(champion: Champion, level: int) -> ListedChampion:
    """Locks the champion at `level` (0 unlocks them)."""
    write_lock(STORE, champion.id, level)
    return listed(champion, level)


def listed(champion: Champion, lock: int) -> ListedChampion:
    return ListedChampion(champion_row(champion), slot_value(champion), lock)


@dataclass(frozen=True)
class OnlyView:
    """The dialog's fixed filter: its fields (name, value) and, in words, what it admits."""

    fields: list[tuple[str, str]]
    label: str


def only_view(restriction: Restriction) -> OnlyView:
    fields = [("only_faction", f) for f in restriction.factions]
    fields += [("only_role", r) for r in restriction.roles]
    fields += [("only_rarity", r) for r in restriction.rarities]
    fields += [("only_affinity", a) for a in restriction.affinities]
    fields += [("only_grade", str(restriction.grade))] if restriction.grade else []
    return OnlyView(fields, restriction_label(restriction))


ROLE_NAMES = {"Attack": "ATK", "Defense": "DEF", "Health": "HP", "Support": "Support"}


def restriction_label(restriction: Restriction) -> str:
    """ "Magic, ATK, 6★ champions"; a race (unchecked) is named after."""
    parts = [
        " or ".join(faction_label(f) for f in restriction.factions),
        " or ".join(restriction.affinities),
        " or ".join(ROLE_NAMES.get(r, r) for r in restriction.roles),
        " or ".join(restriction.rarities),
        f"{restriction.grade}★" if restriction.grade else "",
    ]
    text = ", ".join(p for p in parts if p) or "any"
    return f"{text} champions" + (f" ({restriction.race}: not checked)" if restriction.race else "")


def account_factions(account: Account) -> tuple[str, ...]:
    """The factions the account has champions of, by display name."""
    return tuple(sorted({faction_name(c.faction) for c in account.champions.values()}))
