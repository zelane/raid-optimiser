"""
finder.py - the champion finder's query into a `FinderQuery`.

Fields: `q`, part of a name; `rarity`, one of the game's rarities (anything else: any);
`faction`, a faction's display name (one the account has none of: any, `find_champions`
decides); `grade`, the fewest stars (1-6; anything else: any). A page can hold the list to
what a stage admits (`Restriction`): `only_faction`, `only_role`, `only_rarity`,
`only_affinity` (repeated, the game's names) and `only_grade`. Nothing fails: the finder
always lists something.

- `RARITIES`, `GRADES`: what the filters offer
- `FinderQuery`: the parsed query
- `parse_finder_query` (`parse_only`): the boundary
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.enemies import Restriction

RARITIES = ("Mythical", "Legendary", "Epic", "Rare", "Uncommon", "Common")
GRADES = (6, 5, 4, 3, 2, 1)


@dataclass(frozen=True)
class FinderQuery:
    text: str = ""
    rarity: str | None = None
    faction: str | None = None
    min_grade: int = 0
    only: Restriction | None = None  # what the page's stage admits


def parse_finder_query(
    query: Mapping[str, str], lists: Mapping[str, list[str]] | None = None
) -> FinderQuery:
    """`lists`: each repeated field's values (the `only_` ones)."""
    rarity = query.get("rarity", "")
    grade = query.get("grade", "")
    return FinderQuery(
        text=query.get("q", "").strip(),
        rarity=rarity if rarity in RARITIES else None,
        faction=query.get("faction", "").strip() or None,
        min_grade=int(grade) if grade.isdigit() and int(grade) in GRADES else 0,
        only=parse_only(lists or {}),
    )


def parse_only(lists: Mapping[str, list[str]]) -> Restriction | None:
    def values(name: str) -> tuple[str, ...]:
        return tuple(v for v in lists.get(f"only_{name}", []) if v)

    grade = "".join(lists.get("only_grade", [])[-1:])
    only = Restriction(
        factions=values("faction"),
        roles=values("role"),
        rarities=values("rarity"),
        affinities=values("affinity"),
        grade=int(grade) if grade.isdigit() else None,
    )
    return only if only != Restriction((), (), (), ()) else None
