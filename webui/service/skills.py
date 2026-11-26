"""
skills.py - a form's skills as the pages name them: where each sits in its form's skill list (A1,
A2 …, P1, P2 …) and how far it's booked. A skill's top is one past how many books the game
defines for it (a book a level), so a skill with none is already there.

- `SLOT_KINDS`: the game's skill group -> how the pages label its skills
- `SkillLevel`: the view
- `form_skills`: a form's skills in slot order, each at its level
- `slot_labels`, `slot_order`, `top_level`, `booked_cooldown`: their pieces

The skill books page (`service.books`) and the champion page (`service.champions`) share them.
"""

from dataclasses import dataclass

from optimiser.account import HeroForm, Skill, Tables

SLOT_KINDS = {"Active": "A", "Passive": "P"}  # numbered in order: A1, A2 …, P1, P2 …


@dataclass(frozen=True)
class SkillLevel:
    """A skill where it sits (`slot`: A1, A2 …, P1, P2 …), its name and the game's text for it,
    the level it's at and the level all its books reach (1: it takes none), and its cooldown in
    turns, as the game defines it and after the books it's had (0: none)."""

    slot: str
    name: str
    description: str
    level: int
    top: int
    base_cooldown: int
    cooldown: int


def form_skills(form: HeroForm, levels: dict[int, int], tables: Tables) -> list[SkillLevel]:
    """The form's skills in slot order, each at the champion's level (`Champion.skill_levels`): a
    skill the champion has no record of simply hasn't had any books."""
    slots = slot_labels(form, tables)

    return sorted(
        (
            SkillLevel(
                slots[skill_id],
                skill.name,
                skill.description,
                level,
                top_level(skill),
                skill.cooldown,
                booked_cooldown(skill, level),
            )
            for skill_id in form.skills
            if (skill := tables.skills.get(skill_id)) and (level := levels.get(skill_id, 1))
        ),
        key=lambda skill: slot_order(skill.slot),
    )


def slot_labels(form: HeroForm, tables: Tables) -> dict[int, str]:
    """Where each of a form's skills sits, numbered in order: its actives A1, A2, A3 …, its
    passives P1, P2 …"""
    labels: dict[int, str] = {}
    so_far = dict.fromkeys(SLOT_KINDS, 0)

    for skill_id in form.skills:
        skill = tables.skills.get(skill_id)
        kind = "Active" if skill and skill.group == "Active" else "Passive"
        so_far[kind] += 1
        labels[skill_id] = f"{SLOT_KINDS[kind]}{so_far[kind]}"

    return labels


def slot_order(slot: str) -> tuple[int, int]:
    """A1, A2, A3 …, then P1, P2 …: the kind first, its number after."""
    return (0 if slot[0] == SLOT_KINDS["Active"] else 1, int(slot[1:]))


def top_level(skill: Skill) -> int:
    """The level all a skill's books reach: a book is a level past 1, and a skill the game gives
    no books to is already there."""
    return len(skill.books) + 1


def booked_cooldown(skill: Skill, level: int) -> int:
    """The skill's cooldown after the books it's had (the first level - 1), each cooldown book
    a turn less."""
    taken = skill.books[: level - 1]
    turns = sum(round(book.value) for book in taken if book.type == "CooltimeTurn")

    return max(skill.cooldown - turns, 0)
