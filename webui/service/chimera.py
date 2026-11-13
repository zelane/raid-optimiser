"""
chimera.py - the Chimera trials page: for the column holding this rotation's mythical
materials, teams of five that clear its nine trials (Ram, Lion and Snake; Easy, Normal and
Hard) in one Ultra Nightmare fight, judged on what their skills can place and do.

- `DEFAULT_COLUMN`, `GRADES`: what the page opens on and offers
- `NeedView`, `TrialView`, `FormRow`, `TeamView`, `ChimeraPage`: the views
- `chimera_page`: what the page asks for
- `team_view`, `trial_view`, `describe_target`: its pieces
"""

from dataclasses import dataclass

from optimiser.account import Account
from optimiser.chimera import ANIMAL_FORMS, LEVELS, PARTS, Team, TrialCover, plan_teams
from optimiser.enemies import Enemies, Trial
from webui.service.views import ChampionRow, champion_row

DEFAULT_COLUMN = "Tail"  # where the game's data puts Ultra Nightmare's mythical materials
GRADES = (6, 5, 4)
TEAMS = 5


@dataclass(frozen=True)
class NeedView:
    label: str
    met: bool
    by: list[str]  # who on the team brings it (for counts: which effects)


@dataclass(frozen=True)
class TrialView:
    level: str
    description: str
    target: str  # "2,000,000 damage", "7"
    met: bool
    needs: list[NeedView]


@dataclass(frozen=True)
class FormRow:
    form: str
    trials: list[TrialView]  # Easy, Normal, Hard


@dataclass(frozen=True)
class TeamView:
    core: list[ChampionRow]
    flexible: list[ChampionRow]  # any champion would do in their place
    cleared: int
    total: int
    rows: list[FormRow]


@dataclass(frozen=True)
class ChimeraPage:
    column: str
    columns: tuple[str, ...]
    min_grade: int
    grades: tuple[int, ...]
    candidates: int
    teams: list[TeamView]
    problems: list[str]  # where the trial needs disagree with the game's data


def chimera_page(account: Account, enemies: Enemies, column: str, min_grade: int) -> ChimeraPage:
    """`column` must be one of `PARTS`."""
    plan = plan_teams(account, enemies, column, min_grade, TEAMS)
    return ChimeraPage(
        column=column,
        columns=PARTS,
        min_grade=min_grade,
        grades=GRADES,
        candidates=plan.candidates,
        teams=[team_view(team) for team in plan.teams],
        problems=list(plan.problems),
    )


def team_view(team: Team) -> TeamView:
    by_form = {form: [c for c in team.trials if c.trial.form == form] for form in ANIMAL_FORMS}
    rows = [
        FormRow(form, [trial_view(c) for c in sorted(covers, key=level_order)])
        for form, covers in by_form.items()
    ]
    return TeamView(
        core=[champion_row(c) for c in team.core],
        flexible=[champion_row(c) for c in team.flexible],
        cleared=team.cleared,
        total=len(team.trials),
        rows=rows,
    )


def level_order(cover: TrialCover) -> int:
    return LEVELS.index(cover.trial.level)


def trial_view(cover: TrialCover) -> TrialView:
    return TrialView(
        level=cover.trial.level,
        description=cover.trial.description,
        target=describe_target(cover.trial),
        met=cover.met,
        needs=[NeedView(n.label, n.met, list(n.by)) for n in cover.needs],
    )


def describe_target(trial: Trial) -> str:
    amount = f"{trial.target:,.0f}"
    return f"{amount} damage" if trial.damage else amount
