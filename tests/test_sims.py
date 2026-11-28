"""
test_sims.py - the sim page's team: posted as JSON, parsed at the boundary, named in the
result, and passed to the host as a saved team's skill settings would be. Needs the account
snapshot (`just read`).

- `test_a_saved_team_round_trips`: a saved team, posted unchanged, is that team, with the same
  skill settings the host would take from it
- `test_an_edit_is_named`: a changed priority makes it "…, edited"
- `test_bad_teams_are_refused`: unknown or doubled champions, bad priorities, too many slots
- `test_the_stage_sets_the_team_size`: a Hydra team of six fits a stage taking six, not five
"""

import json

import pytest

from optimiser.account import Account, Preset
from optimiser.paths import GAME, SCHEMA, SNAPSHOT
from optimiser.setups import preset_settings, skill_settings
from webui.forms.common import FormErrors
from webui.forms.sims import SimRun, parse_sim_run
from webui.service.sims import team_label, team_options
from webui.sims import settings_json


@pytest.fixture(scope="module")
def account() -> Account:
    if not SNAPSHOT.exists():
        pytest.skip("no account snapshot (just read)")

    from optimiser.account import load_account

    return load_account(SNAPSHOT, GAME, SCHEMA)


def saved_team(account: Account) -> Preset:
    """A saved team of five with settings for each wave."""
    return next(
        p
        for p in account.presets
        if len([i for i in p.champion_ids if i in account.champions]) == 5 and p.skill_settings
    )


def posted(account: Account, preset: Preset, edit=lambda slots: slots) -> dict[str, str]:
    """The page's form for the saved team as it loads it, after `edit`."""
    option = next(o for o in team_options(account) if o.id == preset.id)
    slots = [
        {
            "champion": s.champion.id,
            "waves": [{"openers": list(w.openers), "priorities": w.priorities} for w in s.waves],
        }
        for s in option.slots
    ]
    return {"team": str(preset.id), "runs": "6", "target": "", "slots": json.dumps(edit(slots))}


def test_a_saved_team_round_trips(account: Account) -> None:
    preset = saved_team(account)
    run = parse_sim_run(posted(account, preset), account, 5)

    assert isinstance(run, SimRun)
    assert team_label(account, preset.id, run.slots) == preset.name

    snapshot = json.loads(SNAPSHOT.read_text())
    sent, saved = settings_json(run.slots), preset_settings(snapshot, preset.id)
    for slot in run.slots:
        assert skill_settings(sent, slot.champion_id) == skill_settings(saved, slot.champion_id)


def test_an_edit_is_named(account: Account) -> None:
    preset = saved_team(account)

    def never_use_a1(slots: list[dict]) -> list[dict]:
        a1 = next(iter(slots[0]["waves"][0]["priorities"]), None) or "1"
        slots[0]["waves"][0]["priorities"] = {a1: "NotUsed"}
        return slots

    run = parse_sim_run(posted(account, preset, never_use_a1), account, 5)

    assert isinstance(run, SimRun)
    assert team_label(account, preset.id, run.slots) == f"{preset.name}, edited"


@pytest.mark.parametrize(
    "edit",
    [
        lambda slots: slots + [slots[0]],  # a champion twice (and more than the stage takes)
        lambda slots: [slots[0], slots[0]],  # a champion twice
        lambda slots: [{**slots[0], "champion": -5}],  # no such champion
        lambda slots: [{**slots[0], "waves": [{"openers": [], "priorities": {"1": "Often"}}]}],
        lambda _: [],
    ],
)
def test_bad_teams_are_refused(account: Account, edit) -> None:
    run = parse_sim_run(posted(account, saved_team(account), edit), account, 5)
    assert isinstance(run, FormErrors)


def test_the_stage_sets_the_team_size(account: Account) -> None:
    hydra = next(
        p
        for p in account.presets
        if p.area == "Hydra" and len([i for i in p.champion_ids if i in account.champions]) == 6
    )

    assert isinstance(parse_sim_run(posted(account, hydra), account, 6), SimRun)
    assert isinstance(parse_sim_run(posted(account, hydra), account, 5), FormErrors)
