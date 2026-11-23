"""
runs.py - a champion's runs, kept in the store: what was asked, in a line, and the outcome
view as `dataclasses.asdict` JSON, revived into views (or None once the views have changed
shape).

- `HISTORY_LIMIT`, `GEAR_SEPARATOR`, `NO_BUILD`: how runs are listed and summed up
- `RunEntryView`, `RunView`: a run, as listed and in full
- `record_run`, `run_history`, `saved_run`, `forget_run`, `last_solved`: what the pages ask for
- `describe_request`, `describe_ranked`, `outcome_note`: a run's summary and note
- `outcome_json`, `revive_outcome`, `revive`, `revive_value`: outcomes saved and revived
- `run_view`, `entry_view`: what they share
"""

import types
import typing
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime

from optimiser.account import Account, Champion
from optimiser.accuracy import Lands, Resists
from optimiser.damage import DamageGoal
from optimiser.labels import STAT_LABELS, format_stat, gear_filter_label
from optimiser.paths import STORE
from optimiser.solve import Goal, Request
from optimiser.store import (
    NewRun,
    Run,
    RunEntry,
    delete_run,
    latest_champion,
    list_runs,
    read_run,
    save_run,
)
from webui.service.results import Outcome, ResultsView, ShortfallView
from webui.service.views import champion_row

HISTORY_LIMIT = 30  # runs listed per champion
GEAR_SEPARATOR = " · gear: "  # `describe_request`'s last part
NO_BUILD = "no build"  # `outcome_note` when nothing was found


@dataclass(frozen=True)
class RunEntryView:
    """`summary` is what was asked, `gear` the gear it left out ("gear: …", or "" in
    runs from before it was noted); `found`: whether it found a build."""

    id: int
    ran_at: str  # local time, "08 Nov 14:03"
    summary: str
    gear: str
    note: str
    found: bool


@dataclass(frozen=True)
class RunView:
    """A saved run. `outcome` is None when it was saved in a shape these views no longer
    have."""

    entry: RunEntryView
    form: dict[str, str]
    outcome: Outcome | None


def record_run(
    account: Account, form: dict[str, str], request: Request, outcome: Outcome
) -> RunView:
    run = NewRun(
        champion_id=request.champion.id,
        summary=describe_request(request, account),
        note=outcome_note(outcome),
        form=form,
        outcome=outcome_json(outcome),
    )
    return run_view(save_run(STORE, run, datetime.now(UTC)), request.champion)


def run_history(champion: Champion) -> list[RunEntryView]:
    """Newest first."""
    return [entry_view(entry) for entry in list_runs(STORE, champion.id, HISTORY_LIMIT)]


def saved_run(champion: Champion, run_id: int) -> RunView | None:
    """None when the champion has no such run."""
    run = read_run(STORE, champion.id, run_id)
    return run_view(run, champion) if run else None


def forget_run(champion: Champion, run_id: int) -> None:
    delete_run(STORE, champion.id, run_id)


def last_solved() -> int | None:
    """The champion the newest run was for."""
    return latest_champion(STORE)


def describe_request(request: Request, account: Account) -> str:
    """ "HP › SPD · SPD ≥ 200 · Lethal 4 · gear: locked up to 2 · battle: SPD 30%, Roric
    Wyrmbane's aura", led by the form for champions with several ("Health form · HP › ...")."""
    champion = request.champion
    forms = account.tables.hero_forms.get(champion.type_id, ())
    form = [f"{forms[champion.form].role} form"] if len(forms) > 1 else []
    at_least = [
        f"{STAT_LABELS[stat]} ≥ {format_stat(stat, value)}"
        for stat, value in request.minimums.items()
    ]
    at_most = [
        f"{STAT_LABELS[stat]} ≤ {format_stat(stat, value)}"
        for stat, value in request.maximums.items()
    ]
    sets = [
        f"{account.tables.sets[set_id].name} {pieces}"
        for set_id, pieces in request.set_minimums.items()
    ]
    ranking = " › ".join(describe_ranked(goal) for goal in request.ranking)
    gear = f"gear: {gear_filter_label(request.gear, account)}"
    battle = request.battle
    assumed = [f"{STAT_LABELS[buff.stat]} {buff.percent}%" for buff in battle.buffs]
    assumed += [f"{battle.leader.champion.name}'s aura"] if battle.leader else []
    in_battle = [f"battle: {', '.join(assumed)}"] if assumed else []

    return " · ".join([*form, ranking, *at_least, *at_most, *sets, gear, *in_battle])


def describe_ranked(goal: Goal) -> str:
    match goal:
        case DamageGoal(skill_name=skill_name):
            return f"{skill_name} DMG"

        case Lands(resistance=resistance):
            return f"debuffs land vs {resistance:g} RES"

        case Resists(accuracy=accuracy):
            return f"resists {accuracy:g} ACC"

        case stat:
            return STAT_LABELS[stat]


def outcome_note(outcome: Outcome) -> str:
    match outcome:
        case ResultsView(builds=builds):
            return f"{len(builds)} build{'s' if len(builds) != 1 else ''}"

        case ShortfallView():
            return NO_BUILD


def outcome_json(outcome: Outcome) -> dict:
    return {"kind": type(outcome).__name__, "view": asdict(outcome)}


def revive_outcome(saved: dict) -> Outcome | None:
    """The outcome `outcome_json` saved, or None if the views have changed shape since."""
    kinds = {"ResultsView": ResultsView, "ShortfallView": ShortfallView}

    try:
        return revive(kinds[saved["kind"]], saved["view"])
    except (KeyError, TypeError, ValueError):
        return None


def revive[T](cls: type[T], data: dict) -> T:
    """A view `asdict` saved, rebuilt with its nested views; fields the view has since
    dropped are left out, and it raises on fields that don't fit."""
    hints = typing.get_type_hints(cls)
    kept = {name: value for name, value in data.items() if name in hints}
    return cls(**{name: revive_value(hints[name], value) for name, value in kept.items()})


def revive_value(hint: object, value: object) -> object:
    origin = typing.get_origin(hint)

    if value is None:
        return None

    if origin in (typing.Union, types.UnionType):
        (inner,) = [arm for arm in typing.get_args(hint) if arm is not type(None)]
        return revive_value(inner, value)

    if origin is list and isinstance(value, list):
        (item_hint,) = typing.get_args(hint)
        return [revive_value(item_hint, item) for item in value]

    if isinstance(hint, type) and is_dataclass(hint) and isinstance(value, dict):
        return revive(hint, value)

    return value


def run_view(run: Run, champion: Champion) -> RunView:
    """Results show the champion as they are now (a portrait extracted since, say)."""
    match revive_outcome(run.outcome):
        case ResultsView() as results:
            outcome = replace(results, champion=champion_row(champion))

        case other:
            outcome = other

    return RunView(entry_view(run.entry), run.form, outcome)


def entry_view(entry: RunEntry) -> RunEntryView:
    ran_at = entry.ran_at.astimezone().strftime("%d %b %H:%M")
    summary, _, gear = entry.summary.partition(GEAR_SEPARATOR)
    found = entry.note != NO_BUILD
    return RunEntryView(entry.id, ran_at, summary, gear and f"gear: {gear}", entry.note, found)
