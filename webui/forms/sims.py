"""
sims.py - the sim page's fields into a `SimAsk`: the page's query, and the run's posted form
alike.

Fields: `team` (a saved team's id; empty: none picked yet), `runs` (how many fights, 1 to
`MAX_RUNS`; empty: `DEFAULT_RUNS`), `target` (the target picker's pick: its stage is the
opponent).

- `DEFAULT_RUNS`, `MAX_RUNS`: the run count's default and limit
- `SimAsk`: what's asked
- `parse_sim_ask`: the boundary
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account
from webui.forms.common import FormErrors

DEFAULT_RUNS = 300
MAX_RUNS = 3000


@dataclass(frozen=True)
class SimAsk:
    team: int | None
    runs: int
    target: str


def parse_sim_ask(form: Mapping[str, str], account: Account) -> SimAsk | FormErrors:
    errors = []
    team_text = form.get("team", "").strip()
    runs_text = form.get("runs", "").strip()
    team = int(team_text) if team_text.isdigit() else None
    runs = int(runs_text) if runs_text.isdigit() else DEFAULT_RUNS

    if team_text and (team is None or account.preset(team) is None):
        errors.append(f"team: no saved team {team_text!r}")

    if runs_text and not (runs_text.isdigit() and 1 <= runs <= MAX_RUNS):
        errors.append(f"runs: {runs_text!r} isn't a number from 1 to {MAX_RUNS}")

    if errors:
        return FormErrors(errors)

    return SimAsk(team, runs, form.get("target", "").strip())
