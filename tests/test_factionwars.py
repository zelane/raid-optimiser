"""
test_factionwars.py - a Faction Wars challenge as needs (`optimiser.factionwars`), and the
team finder's counts (`forms.team.parse_counts`).

- `test_placing_debuffs_asks_for_the_debuff`, `test_debuff_counts_count_instances`,
  `test_effects_and_mechanics`: what a challenge's text asks for
- `test_fights_arent_read`: what isn't
- `test_counts_parse`: "debuff:3" as three different debuffs
"""

from optimiser.factionwars import COUNTER, challenge_needs
from optimiser.teams.needs import AnyOf, Distinct
from optimiser.teams.tags import Side, Tag, buff, debuff
from webui.forms.common import FormErrors
from webui.forms.team import parse_counts


def test_placing_debuffs_asks_for_the_debuff() -> None:
    assert challenge_needs("Place 10+ Stun debuffs") == (AnyOf(debuff("Stun")),)
    assert challenge_needs("Place 20+ Poison debuffs on enemies") == (
        AnyOf(debuff("ContinuousDamage")),
    )
    assert challenge_needs("Place 12+ HP Burn debuffs") == (AnyOf(debuff("Burn")),)
    assert challenge_needs("Place 4+ Taunt buffs") == (AnyOf(buff("Taunt")),)
    assert challenge_needs("Defeat 6+ enemies while they're under Hex debuffs") == (
        AnyOf(debuff("Mark")),
    )


def test_debuff_counts_count_instances() -> None:
    assert challenge_needs("Defeat 3+ enemies while they're under 7 or more debuffs") == (
        Distinct(Side.DEBUFF, 7, instances=True),
    )
    assert challenge_needs("Defeat 3+ enemies while your Champions are under 5 or more buffs") == (
        Distinct(Side.BUFF, 5),
    )


def test_effects_and_mechanics() -> None:
    assert challenge_needs("Get an Extra Turn 5+ times") == (
        AnyOf(frozenset({Tag(Side.EFFECT, "ExtraTurn")})),
    )
    assert challenge_needs("Defeat 3+ enemies using Ally Attack skills or counterattacks") == (
        AnyOf(COUNTER),
    )


def test_fights_arent_read() -> None:
    assert challenge_needs("Clear the Stage in 125 turns") is None
    assert challenge_needs("Use at least 3 Epic Champions") is None
    assert challenge_needs("Place 10+ Mystery debuffs") is None  # a debuff the table doesn't know


def test_counts_parse() -> None:
    assert parse_counts(["debuff:3", "buff:2"]) == (
        Distinct(Side.DEBUFF, 3),
        Distinct(Side.BUFF, 2),
    )
    assert parse_counts(["debuff:3", "debuff:5"]) == (Distinct(Side.DEBUFF, 5),)
    assert isinstance(parse_counts(["effect:3"]), FormErrors)
    assert isinstance(parse_counts(["debuff:0"]), FormErrors)
