"""
test_finder.py - the champion finder's query (`parse_finder_query`).

- `test_query_reads_its_fields`: name, rarity and fewest stars as given
- `test_unknown_values_fall_back_to_any`: a rarity or star count the game doesn't have means any
"""

from webui.forms.finder import FinderQuery, parse_finder_query


def test_query_reads_its_fields() -> None:
    query = parse_finder_query({"q": "  Taur ", "rarity": "Epic", "grade": "5"})

    assert query == FinderQuery(text="Taur", rarity="Epic", min_grade=5)


def test_unknown_values_fall_back_to_any() -> None:
    query = parse_finder_query({"rarity": "Shiny", "grade": "9"})

    assert query == FinderQuery()
    assert parse_finder_query({"grade": "-1"}) == FinderQuery()
