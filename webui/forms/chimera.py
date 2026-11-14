"""
chimera.py - the Chimera page's query: `column` (one of `PARTS`), `min_grade`, `run` (search
around the slots) with `listed` and `option`, and the team's fields (`forms.team`: slots,
wants, gear, assumptions).

- `DEFAULT_COLUMN`, `GRADES`, `FIRST_SHOWN`, `MAX_LISTED`: the page's shape
- `Fill`, `ChimeraRequest`, `Unknown`: what it asks
- `parse_chimera`: the boundary
- `parse_fill`: its step
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account
from optimiser.chimera.trials import PARTS, TEAM_SIZE
from webui.forms.common import FormErrors
from webui.forms.team import Offers, TeamAsk, parse_team

# Where the mythical materials are at prize offset 0, if the game doesn't say.
DEFAULT_COLUMN = "Tail"
GRADES = (6, 5, 4)
FIRST_SHOWN = 3  # teams a run lists at first
MAX_LISTED = 300  # most a page lists
TRUE = ("true", "1", "on", "yes")


@dataclass(frozen=True)
class Fill:
    """Search for teams around the slots: list the first `listed`, the trials showing option
    number `option` (the first, if there's no such option)."""

    listed: int
    option: int


@dataclass(frozen=True)
class ChimeraRequest:
    """What the Chimera page asks for: the rotation's column (one of `PARTS`), the champions
    to search from (`min_grade`★ up), the team (its slots, what it must bring besides the
    trials, what it can wear or is assumed to have), and `fill`: a search (None: the slots
    as they are)."""

    column: str
    min_grade: int
    team: TeamAsk
    fill: Fill | None


@dataclass(frozen=True)
class Unknown:
    """The page asked for doesn't exist (a column or rank there isn't)."""

    reason: str


def parse_chimera(
    query: Mapping[str, list[str]], account: Account, offers: Offers, rotation: str | None
) -> ChimeraRequest | Unknown | FormErrors:
    """The query's fields (each name's values, in order; a single value is the last). Without
    a column, the rotation's (the game's current raid's), else `DEFAULT_COLUMN`."""

    def last(name: str, default: str) -> str:
        return (query.get(name) or [default])[-1]

    column = last("column", rotation or DEFAULT_COLUMN)
    if column not in PARTS:
        return Unknown(f"no {column} column: {', '.join(PARTS)}")

    grade = last("min_grade", str(GRADES[0]))
    if not grade.isdigit() or int(grade) not in GRADES:
        return Unknown(f"rank {grade} isn't offered")

    team = parse_team(query, account, offers, TEAM_SIZE)
    if isinstance(team, FormErrors):
        return team

    return ChimeraRequest(
        column=column,
        min_grade=int(grade),
        team=team,
        fill=parse_fill(query) if last("run", "").lower() in TRUE else None,
    )


def parse_fill(query: Mapping[str, list[str]]) -> Fill:
    """How many teams to list (`FIRST_SHOWN` to `MAX_LISTED`) and which to show; numbers that
    aren't fall back to the first."""

    def number(name: str, default: int) -> int:
        text = (query.get(name) or [""])[-1]
        return int(text) if text.isdigit() else default

    listed = min(max(number("listed", FIRST_SHOWN), FIRST_SHOWN), MAX_LISTED)
    return Fill(listed, number("option", 1))
