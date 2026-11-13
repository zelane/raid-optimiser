"""
reserve.py - gear kept for something else, worked out from the account: what champions with
a tag wear (Arena Build I), what the global gear presets hold, and what a saved team's
champions wear (the Demon Lord team). Which rules apply is the user's (the store holds them by
`rule_key`); what they reserve comes fresh from each snapshot.

A piece in a global preset stays reserved even when no one wears it, or someone else does: the
preset expects to get it back. A champion's own gear is never reserved against them (the
solver allows it first).

- `Tagged`, `GlobalPresets`, `Team`, `Rule`: the rules
- `Reason`, `Reservations`: why a piece is reserved
- `reservations`: every reserved piece, with its reasons (`reserved_by`, `worn_by`: its steps)
- `rule_key`, `parse_rule`: rules as the store and the forms name them ("tag:ArenaFirst",
  "global", "team:14")
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from optimiser.account import Account


@dataclass(frozen=True)
class Tagged:
    """What champions tagged `marker` (the game's `HeroMarker` name) wear."""

    marker: str


@dataclass(frozen=True)
class GlobalPresets:
    """Every piece in a global gear preset."""


@dataclass(frozen=True)
class Team:
    """What the champions of a saved team (`Preset.id`) wear."""

    preset_id: int


type Rule = Tagged | GlobalPresets | Team


@dataclass(frozen=True)
class Reason:
    """A rule that reserves a piece, and through whom: the champion wearing it (tags, teams)
    or the preset holding it."""

    rule: Rule
    champion_id: int | None = None
    preset_name: str | None = None


# Artifact id -> why it's reserved; pieces nothing reserves are absent.
type Reservations = Mapping[int, tuple[Reason, ...]]


def reservations(account: Account, rules: tuple[Rule, ...]) -> dict[int, tuple[Reason, ...]]:
    reasons: dict[int, list[Reason]] = {}

    for rule in rules:
        for artifact_id, reason in reserved_by(account, rule):
            reasons.setdefault(artifact_id, []).append(reason)

    return {artifact_id: tuple(found) for artifact_id, found in reasons.items()}


def reserved_by(account: Account, rule: Rule) -> list[tuple[int, Reason]]:
    match rule:
        case Tagged(marker=marker):
            tagged = [c.id for c in account.champions.values() if c.marker == marker]
            return worn_by(account, rule, tagged)

        case GlobalPresets():
            return [
                (artifact_id, Reason(rule, preset_name=preset.name))
                for preset in account.gear_presets
                for artifact_id in preset.artifact_ids
            ]

        case Team(preset_id=preset_id):
            team = next((p for p in account.presets if p.id == preset_id), None)
            return worn_by(account, rule, team.champion_ids if team else ())


def worn_by(account: Account, rule: Rule, champion_ids: Iterable[int]) -> list[tuple[int, Reason]]:
    return [
        (artifact_id, Reason(rule, champion_id=champion_id))
        for champion_id in champion_ids
        if champion_id in account.champions
        for artifact_id in account.champions[champion_id].artifact_ids
    ]


def rule_key(rule: Rule) -> str:
    match rule:
        case Tagged(marker=marker):
            return f"tag:{marker}"

        case GlobalPresets():
            return "global"

        case Team(preset_id=preset_id):
            return f"team:{preset_id}"


def parse_rule(key: str) -> Rule | None:
    """None for a key `rule_key` never gives."""
    match key.split(":"):
        case ["tag", marker] if marker:
            return Tagged(marker)

        case ["global"]:
            return GlobalPresets()

        case ["team", preset_id] if preset_id.lstrip("-").isdigit():
            return Team(int(preset_id))

        case _:
            return None
