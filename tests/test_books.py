"""
test_books.py - the skill books page: what each form still wants (`forms_short`), what the
books left give (`book_gains`), and its query's defaults (`parse_books_query`).

- `test_forms_short_counts_each_form_apart`: a mythical's forms take their own books; a skill
  booked to its top, or with no books at all, wants none
- `test_skills_are_labelled_by_kind_and_place`: A1, A2 … then P1 …, whatever the list's order
- `test_book_gains_sums_the_books_left`: only the books from the skill's level up, each kind
  summed, cooldown in turns
- `test_query_starts_on_the_defaults`: a URL without rarity or stars gets the page's
- `test_query_reads_any`: `ANY` lifts a default; other values pass through
"""

from types import SimpleNamespace
from typing import cast

from optimiser.account import Champion
from optimiser.tables import Book, HeroForm, Skill, Stats, Tables
from webui.forms.books import ANY, parse_books_query
from webui.forms.finder import FinderQuery
from webui.service.books import book_gains, forms_short

DAMAGE = Book("Attack", 0.05)
COOLDOWN = Book("CooltimeTurn", 1)


def skill(skill_id: int, group: str, *books: Book) -> Skill:
    return Skill(skill_id, f"Skill {skill_id}", group, False, (), (), books=books)


def form(*skills: int) -> HeroForm:
    return HeroForm("Attack", skills, cast(Stats, None))


def account_of(forms: tuple[HeroForm, ...], skills: list[Skill], levels: dict[int, int]):
    tables = cast(
        Tables,
        SimpleNamespace(hero_forms={7: forms}, skills={s.id: s for s in skills}),
    )
    champion = cast(Champion, SimpleNamespace(type_id=7, skill_levels=levels))
    return champion, tables


def test_forms_short_counts_each_form_apart() -> None:
    skills = [
        skill(1, "Active", DAMAGE, DAMAGE),  # booked to its top
        skill(2, "Passive"),  # no books: already there
        skill(3, "Active", DAMAGE, COOLDOWN),
        skill(4, "Active", DAMAGE),
    ]
    champion, tables = account_of((form(1, 2, 3), form(4)), skills, {1: 3, 3: 2})

    shorts = forms_short(champion, tables)

    assert [(f.form, f.forms, f.short) for f in shorts] == [(1, 2, 1), (2, 2, 1)]
    assert [(s.slot, s.level, s.top) for s in shorts[0].skills] == [("A2", 2, 3)]
    assert [(s.slot, s.level, s.top) for s in shorts[1].skills] == [("A1", 1, 2)]


def test_skills_are_labelled_by_kind_and_place() -> None:
    skills = [skill(1, "Passive", DAMAGE), skill(2, "Active", DAMAGE), skill(3, "Active", DAMAGE)]
    champion, tables = account_of((form(1, 2, 3),), skills, {})

    (only,) = forms_short(champion, tables)

    assert [s.slot for s in only.skills] == ["A1", "A2", "P1"]
    assert only.forms == 1 and only.short == 3


def test_book_gains_sums_the_books_left() -> None:
    booked = skill(1, "Active", DAMAGE, DAMAGE, COOLDOWN, DAMAGE, COOLDOWN)

    assert book_gains(booked, 1) == ["+15% damage", "2 turns less cooldown"]
    assert book_gains(booked, 3) == ["2 turns less cooldown", "+5% damage"]
    assert book_gains(booked, 5) == ["1 turn less cooldown"]
    assert book_gains(booked, 6) == []


def test_query_starts_on_the_defaults() -> None:
    query = parse_books_query({"q": "Siphi"})

    assert query == FinderQuery(text="Siphi", rarity="Legendary", min_grade=6)


def test_query_reads_any() -> None:
    query = parse_books_query({"rarity": ANY, "grade": ANY, "faction": "Demonspawn"})

    assert query == FinderQuery(faction="Demonspawn")
    assert parse_books_query({"rarity": "Epic", "grade": "5"}).min_grade == 5
