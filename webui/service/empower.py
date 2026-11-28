"""
empower.py - the empower page, for one rarity: the copies safe to feed (a champion already
fully empowered in another copy), those not fully empowered who have fodder, the champions
fully empowered, and every one left to empower. A champion is a type with its ascensions
together (they're each a type of their own); its fodder is its other copies, or for one only
obtainable once, copies of its substitute (`Tables.empower_substitutes`); never an
empowered copy, which is worth more kept.

- `DEFAULT_RARITY`: the rarity the page opens on
- `SpareCopies`, `ChampionCopies`, `LeftToEmpower`, `EmpowerPage`: the views
- `empower_page`: what the page asks for
- `in_game_order`, `empowerable_rarities`, `max_empower`, `copies_by_champion`, `best_first`,
  `needed_by`: what it shares
"""

from collections import defaultdict
from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.tables import EmpowerSubstitute
from webui.service.champions import RARITY_ORDER, game_order
from webui.service.views import ChampionRow, champion_row

DEFAULT_RARITY = "Epic"


@dataclass(frozen=True)
class SpareCopies:
    """A fully empowered champion's other copies: the most empowered of them, and how many.
    `needed_by`: champions only obtainable once, not yet fully empowered, that these feed."""

    copy: ChampionRow
    count: int
    needed_by: list[str]


@dataclass(frozen=True)
class ChampionCopies:
    """A champion's most empowered copy, its other copies, and (for one only obtainable once)
    the copies of its substitute."""

    champion: ChampionRow
    copies: list[ChampionRow]
    substitutes: list[ChampionRow]
    substitute: str | None  # its name


@dataclass(frozen=True)
class LeftToEmpower:
    champion: ChampionRow  # the most empowered copy
    fodder: int  # other copies, or copies of the substitute
    substitute: str | None


@dataclass(frozen=True)
class EmpowerPage:
    rarity: str
    rarities: list[str]  # the ones the game empowers, lowest first
    max_empower: int
    spare: list[SpareCopies]
    with_fodder: list[ChampionCopies]  # not fully empowered
    full: list[ChampionRow]
    left: list[LeftToEmpower]


def empower_page(account: Account, rarity: str) -> EmpowerPage:
    """`rarity` must be one of `empowerable_rarities`. Of a fully empowered champion, every
    copy but the best is spare, even one also at the top. The spare copies and the champions
    left to empower are in the champion list's order (`game_order`) of the copy shown; the
    other lists are by name."""
    top = max_empower(account, rarity)
    substitutes = account.tables.empower_substitutes
    champions = copies_by_champion(account)
    needs = needed_by(champions, substitutes, top)
    spare: list[tuple[Champion, SpareCopies]] = []
    with_fodder = []
    full = []
    left: list[tuple[Champion, LeftToEmpower]] = []

    for kind, copies in sorted(champions.items(), key=lambda item: item[1][0].name):
        best, *rest = best_first(copies)
        if best.rarity != rarity:
            continue

        if best.empower >= top:
            full.extend(champion_row(c) for c in copies if c.empower >= top)

            if rest:
                copies_left = SpareCopies(champion_row(rest[0]), len(rest), needs.get(kind, []))
                spare.append((rest[0], copies_left))

            continue

        substitute = substitutes.get(kind)
        fed_by = best_first(champions.get(substitute.type_id, [])) if substitute else []
        dupes = [c for c in rest if not c.empower]
        others = [c for c in fed_by if not c.empower]
        name = substitute.name if substitute else None
        left.append((best, LeftToEmpower(champion_row(best), len(dupes) + len(others), name)))

        if dupes or others:
            with_fodder.append(
                ChampionCopies(
                    champion_row(best),
                    [champion_row(c) for c in dupes],
                    [champion_row(c) for c in others],
                    name,
                )
            )

    return EmpowerPage(
        rarity=rarity,
        rarities=empowerable_rarities(account),
        max_empower=top,
        spare=in_game_order(spare),
        with_fodder=with_fodder,
        full=full,
        left=in_game_order(left),
    )


def in_game_order[T](items: list[tuple[Champion, T]]) -> list[T]:
    """The views, in the champion list's order of the champions paired with them."""
    return [view for _, view in sorted(items, key=lambda item: game_order(item[0]), reverse=True)]


def empowerable_rarities(account: Account) -> list[str]:
    return sorted(account.tables.empower, key=lambda rarity: RARITY_ORDER.get(rarity, 0))


def max_empower(account: Account, rarity: str) -> int:
    return len(account.tables.empower[rarity])


def copies_by_champion(account: Account) -> dict[int, list[Champion]]:
    """Copies of each champion, by type id with ascension 0."""
    copies: dict[int, list[Champion]] = defaultdict(list)

    for champion in account.champions.values():
        copies[champion.type_id // 10 * 10].append(champion)

    return copies


def best_first(copies: list[Champion]) -> list[Champion]:
    """The most empowered copy first (the newest, of equals)."""
    return sorted(copies, key=lambda c: (c.empower, *game_order(c)), reverse=True)


def needed_by(
    champions: dict[int, list[Champion]], substitutes: dict[int, EmpowerSubstitute], top: int
) -> dict[int, list[str]]:
    """Substitute type -> the champions it empowers that are owned and not yet at `top`."""
    needs: dict[int, list[str]] = defaultdict(list)

    for kind, substitute in substitutes.items():
        copies = champions.get(kind, [])
        if copies and max(c.empower for c in copies) < top:
            needs[substitute.type_id].append(copies[0].name)

    return needs
