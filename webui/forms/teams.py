"""
teams.py - the team finder page's query: `base` ("stage": what a stage asks, with `target`, the
target picker's pick ("<stage>[:<wave>:<slot>]", else its default) and, for the Chimera,
`column` (one of `PARTS`, else the rotation's); else nothing, only what's asked besides),
`min_grade` (one of `GRADES`), `run` (search around the slots) with `listed` and `option`, and
the team's fields (`forms.team`: slots, wants, counts, gear, assumptions).

- `TEAM_SIZE`: the team's slots
- `Against`, `TeamsRequest`: what it asks
- `parse_against`, `parse_teams`: the boundary (the stage first: what it is decides the offers
  `parse_teams` reads the team's fields against)
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account
from optimiser.chimera.trials import PARTS
from webui.forms.common import FormErrors
from webui.forms.targets import SavedTarget, parse_saved
from webui.forms.team import GRADES, TRUE, Fill, Offers, TeamAsk, parse_fill, parse_team

TEAM_SIZE = 5


@dataclass(frozen=True)
class Against:
    """The stage a team is for: `target`, the picker's pick (None: its default), and `column`,
    the Chimera's trials column (None: the rotation's)."""

    target: SavedTarget | None
    column: str | None


@dataclass(frozen=True)
class TeamsRequest:
    """The stage (None: only what's asked besides), the champions to search from
    (`min_grade`★ up), the team, and `fill`: a search (None: the slots as they are)."""

    against: Against | None
    min_grade: int
    team: TeamAsk
    fill: Fill | None


def last(query: Mapping[str, list[str]], name: str, default: str = "") -> str:
    """A field's value (each name's values, in order; a single value is the last)."""
    return (query.get(name) or [default])[-1]


def parse_against(query: Mapping[str, list[str]]) -> Against | None:
    """A column there isn't is the rotation's; a target there isn't, the picker's default."""
    if last(query, "base") != "stage":
        return None

    column = last(query, "column")
    return Against(parse_saved(last(query, "target")), column if column in PARTS else None)


def parse_teams(
    query: Mapping[str, list[str]], account: Account, offers: Offers
) -> TeamsRequest | FormErrors:
    grade = last(query, "min_grade", str(GRADES[0]))
    if not grade.isdigit() or int(grade) not in GRADES:
        return FormErrors([f"rank {grade} isn't offered"])

    team = parse_team(query, account, offers, TEAM_SIZE)
    if isinstance(team, FormErrors):
        return team

    fill = parse_fill(query) if last(query, "run").lower() in TRUE else None
    return TeamsRequest(parse_against(query), int(grade), team, fill)
