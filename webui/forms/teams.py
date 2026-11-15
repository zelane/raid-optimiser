"""
teams.py - the team finder page's query: `base` ("fw": a Faction Wars stage's challenge, with
`crypt`, the crypt's region id, and `stage`, its number at `difficulty`; else nothing, only
what's asked besides), `min_grade` (one of `GRADES`), `run` (search around the slots) with
`listed` and `option`, and the team's fields (`forms.team`: slots, wants, counts, gear,
assumptions). A crypt or stage there isn't falls back to the first.

- `TEAM_SIZE`: the team's slots
- `FactionWarsBase`, `TeamsRequest`: what it asks
- `parse_teams`: the boundary
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account
from optimiser.factionwars import Crypt
from webui.forms.common import FormErrors
from webui.forms.team import GRADES, TRUE, Fill, Offers, TeamAsk, parse_fill, parse_team

TEAM_SIZE = 5


@dataclass(frozen=True)
class FactionWarsBase:
    """A Faction Wars stage: its crypt, difficulty and number (1 first)."""

    crypt: Crypt
    difficulty: str
    number: int

    @property
    def stage(self) -> int:
        return self.crypt.stages[self.difficulty][self.number - 1]


@dataclass(frozen=True)
class TeamsRequest:
    """The base needs (None: only what's asked besides), the champions to search from
    (`min_grade`★ up), the team, and `fill`: a search (None: the slots as they are)."""

    base: FactionWarsBase | None
    min_grade: int
    team: TeamAsk
    fill: Fill | None


def parse_teams(
    query: Mapping[str, list[str]], account: Account, offers: Offers, crypts: tuple[Crypt, ...]
) -> TeamsRequest | FormErrors:
    """The query's fields (each name's values, in order; a single value is the last)."""

    def last(name: str, default: str) -> str:
        return (query.get(name) or [default])[-1]

    grade = last("min_grade", str(GRADES[0]))
    if not grade.isdigit() or int(grade) not in GRADES:
        return FormErrors([f"rank {grade} isn't offered"])

    team = parse_team(query, account, offers, TEAM_SIZE)
    if isinstance(team, FormErrors):
        return team

    base = parse_base(query, crypts) if last("base", "") == "fw" else None
    fill = parse_fill(query) if last("run", "").lower() in TRUE else None
    return TeamsRequest(base, int(grade), team, fill)


def parse_base(query: Mapping[str, list[str]], crypts: tuple[Crypt, ...]) -> FactionWarsBase:
    """The crypt named (else the first), at the difficulty named (else its last: Hard), its
    stage numbered (else the first)."""
    region = (query.get("crypt") or [""])[-1]
    crypt = next((c for c in crypts if c.region == region), crypts[0])
    difficulty = (query.get("difficulty") or [""])[-1]
    if difficulty not in crypt.stages:
        difficulty = list(crypt.stages)[-1]

    number = (query.get("stage") or [""])[-1]
    count = len(crypt.stages[difficulty])
    chosen = int(number) if number.isdigit() and 1 <= int(number) <= count else 1
    return FactionWarsBase(crypt, difficulty, chosen)
