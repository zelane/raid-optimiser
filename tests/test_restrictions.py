"""
test_restrictions.py - what a stage admits (`optimiser.enemies`).

- `test_admits_every_listed_field`: each listed field must match; empty ones admit any
- `test_one_condition_holds_everyone_several_rotate`: `team_restriction` by condition count
- `test_a_crypt_admits_its_faction`: Faction Wars stages, which list no condition
- `test_renamed_factions_match_champions`: the game's old names (Samurai, Olympians) as keys
- `test_faction_labels`: keys as the game shows them
"""

from dataclasses import dataclass

from optimiser.enemies import Restriction, Rotating, parse_restriction, team_restriction
from optimiser.tables import faction_label


@dataclass(frozen=True)
class Hero:
    faction: str = "DarkElves"
    role: str = "Attack"
    rarity: str = "Epic"
    element: str = "Magic"
    grade: int = 6


@dataclass(frozen=True)
class Staged:
    restrictions: tuple[Restriction, ...]
    area: str | None = "DoomTower"
    region: str | None = None


MAGIC_6 = Restriction((), (), (), ("Magic",), grade=6)


def test_admits_every_listed_field() -> None:
    assert MAGIC_6.admits(Hero())  # type: ignore[arg-type]
    assert not MAGIC_6.admits(Hero(element="Force"))  # type: ignore[arg-type]
    assert not MAGIC_6.admits(Hero(grade=5))  # type: ignore[arg-type]
    assert Restriction((), (), (), ()).admits(Hero(rarity="Rare"))  # type: ignore[arg-type]


def test_one_condition_holds_everyone_several_rotate() -> None:
    other = Restriction(("Orcs",), (), (), ())
    assert team_restriction(Staged(())) is None  # type: ignore[arg-type]
    assert team_restriction(Staged((MAGIC_6,))) == MAGIC_6  # type: ignore[arg-type]
    assert team_restriction(Staged((MAGIC_6, other))) == Rotating((MAGIC_6, other))  # type: ignore[arg-type]


def test_a_crypt_admits_its_faction() -> None:
    crypt = Staged((), area="Fractions", region="Fraction_DarkElves")
    restriction = team_restriction(crypt)  # type: ignore[arg-type]

    assert restriction == Restriction(("DarkElves",), (), (), ())
    assert restriction.admits(Hero())  # type: ignore[arg-type]
    assert not restriction.admits(Hero(faction="Orcs"))  # type: ignore[arg-type]


def test_renamed_factions_match_champions() -> None:
    raw = {"factions": ["Samurai", "Olympians"], "roles": None, "rarities": None}
    restriction = parse_restriction(raw | {"affinities": None})
    crypt = Staged((), area="Fractions", region="Fraction_Samurai")

    assert restriction.factions == ("Shadowkin", "Argonites")
    assert team_restriction(crypt) == Restriction(("Shadowkin",), (), (), ())  # type: ignore[arg-type]
    assert restriction.admits(Hero(faction="Shadowkin"))  # type: ignore[arg-type]


def test_faction_labels() -> None:
    assert faction_label("DarkElves") == "Dark Elves"
    assert faction_label("LizardMen") == "Lizardmen"
    assert faction_label("Samurai") == "Shadowkin"
    assert faction_label("Orcs") == "Orcs"
