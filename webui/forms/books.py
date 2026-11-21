"""
books.py - the skill books page's query into a `FinderQuery`: the champion list's filters
(`forms.finder`) with the page's own defaults.

- `DEFAULTS`, `ANY`: what the page filters by until the URL says otherwise, and how the URL
  says "any" to one of them
- `parse_books_query`: the boundary
"""

from collections.abc import Mapping

from webui.forms.finder import FinderQuery, parse_finder_query

DEFAULTS = {"rarity": "Legendary", "grade": "6"}  # top champions of the game's best rarity
ANY = "any"  # Books.vue sends it for a defaulted filter set to any


def parse_books_query(query: Mapping[str, str]) -> FinderQuery:
    """The bar's filters, the page's defaults where the URL leaves one out. The bar always sends
    rarity and stars, `ANY` for any, so one missing means nobody has chosen it yet."""
    defaulted = {name: query.get(name, default) for name, default in DEFAULTS.items()}
    chosen = {name: "" if value == ANY else value for name, value in defaulted.items()}
    return parse_finder_query({**query, **chosen})
