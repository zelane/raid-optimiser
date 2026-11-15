"""
finder.py - the champion finder's query into a `FinderQuery`.

Fields: `q`, part of a name; `rarity`, one of the game's rarities (anything else: any);
`faction`, a faction's display name (one the account has none of: any, `find_champions`
decides); `grade`, the fewest stars (1-6; anything else: any). Nothing fails: the finder
always lists something.

- `RARITIES`, `GRADES`: what the filters offer
- `FinderQuery`: the parsed query
- `parse_finder_query`: the boundary
"""

from collections.abc import Mapping
from dataclasses import dataclass

RARITIES = ("Mythical", "Legendary", "Epic", "Rare", "Uncommon", "Common")
GRADES = (6, 5, 4, 3, 2, 1)


@dataclass(frozen=True)
class FinderQuery:
    text: str = ""
    rarity: str | None = None
    faction: str | None = None
    min_grade: int = 0


def parse_finder_query(query: Mapping[str, str]) -> FinderQuery:
    rarity = query.get("rarity", "")
    grade = query.get("grade", "")
    return FinderQuery(
        text=query.get("q", "").strip(),
        rarity=rarity if rarity in RARITIES else None,
        faction=query.get("faction", "").strip() or None,
        min_grade=int(grade) if grade.isdigit() and int(grade) in GRADES else 0,
    )
