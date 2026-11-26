"""
books.py - the skill books page: the champions whose skills aren't all booked to their top.
A skill's books are whatever the game defines for it (a book a level, so its top is one past how
many it has; a skill with none is already there), and what the unused ones would give is read off
those same books. A champion's two forms (a mythical's) take books of their own, so what each form
still wants is grouped on its own; the reader doesn't say which form the champion is in.

- `BOOK_GAINS`: the game's `SkillBonusType` -> what its book adds
- `SkillShort`, `FormShort`, `ShortOfBooks`, `BooksPage`: the views
- `books_page`: what the page shows
- `forms_short`, `book_gains`: its pieces (skill slots and tops: `service.skills`)

The champion filter bar (`service.finder`) narrows the list; `forms.books` holds its defaults.
"""

from collections import defaultdict
from dataclasses import dataclass

from optimiser.account import Account, Champion, HeroForm, Skill, Tables
from webui.forms.finder import FinderQuery
from webui.service.champions import game_order
from webui.service.finder import FilterChoices, account_factions, filter_choices, matches
from webui.service.skills import slot_labels, slot_order, top_level
from webui.service.views import ChampionRow, champion_row

BOOK_GAINS = {
    "Attack": "damage",
    "Health": "HP",
    "EffectChance": "effect chance",
    "ShieldCreation": "shields",
    "IgnoreResistance": "ignore RES",
}  # CooltimeTurn's a count of turns, worded on its own


@dataclass(frozen=True)
class SkillShort:
    """A skill below its top: where it sits in its form's skill list (`slot`: A1, A2 …, P1, P2 …),
    its name (for telling the skills apart, not shown), the level it's at, the level all its books
    reach, and what the books it hasn't had would give it, one entry per effect."""

    slot: str
    name: str
    level: int
    top: int
    gains: list[str]


@dataclass(frozen=True)
class FormShort:
    """One of a champion's forms that isn't fully booked: `form` of `forms` (1 is all a one-form
    champion has), `short` the books that form still wants, and `skills` those below their top."""

    form: int
    forms: int
    short: int
    skills: list[SkillShort]


@dataclass(frozen=True)
class ShortOfBooks:
    """A champion wanting books: `short` across their forms, `short_forms` those in order."""

    champion: ChampionRow
    short: int
    short_forms: list[FormShort]


@dataclass(frozen=True)
class BooksPage:
    query: FinderQuery  # the champion filter bar's, as the page reads it
    choices: FilterChoices  # and what that bar offers
    matching: int  # how many champions of the filter the account holds
    single: list[ShortOfBooks]  # one book from fully booked, in the champion list's order
    to_book: list[ShortOfBooks]  # the rest, fewest books short first


def books_page(account: Account, query: FinderQuery) -> BooksPage:
    """The champions the filters match, and what their forms still want booked."""
    factions = account_factions(account)
    matched = [
        champion for champion in account.champions.values() if matches(champion, query, factions)
    ]
    short = [
        ShortOfBooks(
            champion_row(champion),
            sum(form.short for form in forms),
            forms,
        )
        for champion in sorted(matched, key=game_order, reverse=True)
        if (forms := forms_short(champion, account.tables))
    ]

    return BooksPage(
        query=query,
        choices=filter_choices(account),
        matching=len(matched),
        single=[entry for entry in short if entry.short == 1],
        to_book=sorted(
            (entry for entry in short if entry.short > 1), key=lambda entry: entry.short
        ),
    )


def forms_short(champion: Champion, tables: Tables) -> list[FormShort]:
    """Each of the champion's forms wanting books: the skills below their top, where each sits in
    that form's skill list, and what the books they haven't had would give them."""
    forms = tables.hero_forms.get(champion.type_id, ())
    entries = []

    for number, form in enumerate(forms, start=1):
        slots = slot_labels(form, tables)
        shorts = sorted(
            (
                SkillShort(
                    slots[skill.id],
                    skill.name,
                    level,
                    top_level(skill),
                    book_gains(skill, level),
                )
                for skill, level in skills_short(form, champion.skill_levels, tables)
            ),
            key=lambda short: slot_order(short.slot),
        )

        if shorts:
            entries.append(
                FormShort(
                    number,
                    len(forms),
                    sum(short.top - short.level for short in shorts),
                    shorts,
                )
            )

    return entries


def skills_short(form: HeroForm, levels: dict[int, int], tables: Tables) -> list[tuple[Skill, int]]:
    """The form's skills that can take books and haven't all had them, with the level each is at:
    a skill the champion has no record of simply hasn't had any."""
    return [
        (skill, levels.get(skill_id, 1))
        for skill_id in form.skills
        if (skill := tables.skills.get(skill_id))
        and top_level(skill) > 1
        and levels.get(skill_id, 1) < top_level(skill)
    ]


def book_gains(skill: Skill, level: int) -> list[str]:
    """What the books this skill hasn't had would give it, each kind summed: '+20% damage',
    '1 turn less cooldown'. The books are in order, so the ones left are from its level up."""
    left: defaultdict[str, float] = defaultdict(float)

    for book in skill.books[level - 1 :]:
        left[book.type] += book.value

    gains = []

    for kind, value in left.items():
        if kind == "CooltimeTurn":
            turns = round(value)
            gains.append(f"{turns} turn{'s' if turns != 1 else ''} less cooldown")
        else:
            gains.append(f"+{round(value * 100, 1):g}% {BOOK_GAINS.get(kind, kind)}")

    return gains
