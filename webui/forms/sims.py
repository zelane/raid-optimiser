"""
sims.py - the sim page's fields into a `SimAsk`: the page's query, and the run's posted form
alike; a run's team (`slots`, posted as JSON) into a `SimRun`.

Fields: `team` (a saved team's id, the one the page loaded; empty: none picked yet), `runs`
(how many fights, 1 to `MAX_RUNS`; empty: `DEFAULT_RUNS`), `target` (the target picker's pick:
its stage is the opponent). A run adds `slots`: the team as the page has it, as many as the
stage takes (`team_size`: Hydra 6, arena 4 …), each
`{"champion": id, "waves": [{"openers": [skill id, …], "priorities": {skill id: name}}, …]}`,
a wave per sequence of the game's skill settings, names the game's `SkillPriorityType`s.

- `DEFAULT_RUNS`, `MAX_RUNS`, `PRIORITIES`: the limits and the names
- `SimAsk`, `SlotAsk`, `SimRun`: what's asked
- `parse_sim_ask`, `parse_sim_run`: the boundary
- `parse_slots`, `parse_slot`, `parse_wave`: a run's team
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account, SkillSettings
from webui.forms.common import FormErrors

DEFAULT_RUNS = 300
MAX_RUNS = 3000
PRIORITIES = ("Default", "First", "Second", "Third", "NotUsed")


@dataclass(frozen=True)
class SimAsk:
    team: int | None
    runs: int
    target: str


@dataclass(frozen=True)
class SlotAsk:
    champion_id: int
    waves: tuple[SkillSettings, ...]


@dataclass(frozen=True)
class SimRun:
    ask: SimAsk
    slots: tuple[SlotAsk, ...]  # at least one


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


def parse_sim_run(form: Mapping[str, str], account: Account, team_size: int) -> SimRun | FormErrors:
    """`team_size`: the stage's (the target's)."""
    match parse_sim_ask(form, account), parse_slots(form.get("slots", ""), account, team_size):
        case FormErrors(messages=asked), FormErrors(messages=slotted):
            return FormErrors(asked + slotted)
        case FormErrors() as errors, _:
            return errors
        case _, FormErrors() as errors:
            return errors
        case SimAsk() as ask, slots:
            return SimRun(ask, slots)


def parse_slots(text: str, account: Account, team_size: int) -> tuple[SlotAsk, ...] | FormErrors:
    try:
        raw = json.loads(text) if text.strip() else []
    except json.JSONDecodeError:
        return FormErrors(["slots: not JSON"])

    if not isinstance(raw, list) or not 1 <= len(raw) <= team_size:
        return FormErrors([f"slots: this stage takes 1 to {team_size} champions"])

    errors: list[str] = []
    slots = tuple(slot for item in raw if (slot := parse_slot(item, account, errors)))
    ids = [slot.champion_id for slot in slots]

    if len(set(ids)) < len(ids):
        errors.append("slots: a champion is in the team twice")

    return FormErrors(errors) if errors else slots


def parse_slot(raw: object, account: Account, errors: list[str]) -> SlotAsk | None:
    match raw:
        case {"champion": int(champion_id), "waves": list(waves)}:
            pass
        case _:
            errors.append(f"slots: {raw!r} isn't a champion and their waves")
            return None

    if champion_id not in account.champions:
        errors.append(f"slots: no champion {champion_id}")
        return None

    settings = tuple(wave for item in waves if (wave := parse_wave(item, errors)))
    return SlotAsk(champion_id, settings) if len(settings) == len(waves) else None


def parse_wave(raw: object, errors: list[str]) -> SkillSettings | None:
    match raw:
        case {"openers": list(openers), "priorities": dict(priorities)} if all(
            isinstance(o, int) for o in openers
        ) and all(k.isdigit() and v in PRIORITIES for k, v in priorities.items()):
            return SkillSettings({int(k): v for k, v in priorities.items()}, tuple(openers))
        case _:
            errors.append(f"slots: {raw!r} isn't a wave's openers and priorities")
            return None
