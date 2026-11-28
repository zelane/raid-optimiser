"""
sims.py - the sim page: a team against a stage, fought many times on the game's own battle
engine (the battle host, `webui.sims` runs it), and the last sim's results: how often it
cleared, the turns a win took, the damage, and each champion's result-screen rows on average.
The team starts as one of the account's saved teams, which the page then changes: champions
swapped in and out, their skill settings (a wave's priorities and openers, as the game's).

- `SkillOption`, `FormSkills`, `WaveSettings`, `SlotView`, `TeamOption`: a team, as the page
  edits it
- `ChampionResult`, `Uncleared`, `TrialRow`, `SimResult`, `SimPage`: the page and its results
- `sim_page`: the page
- `slot_view`: a champion's slot, with their skills and settings (a new one's: auto's defaults)
- `record_result`: a sim just run, summed up and kept (`paths.LAST_SIM`): the page shows it
  whatever the host runs after (`just fight` in a terminal rewrites the host's results)
- `team_label`: what the result calls the team
- `SimProgress`, `sim_progress`: how far the sim under way has got
- `team_options`, `saved_settings`, `form_skills`, `last_result`, `result_view`: its parts
"""

import json
import statistics
import time
from dataclasses import asdict, dataclass

from optimiser.account import Account, Champion, Preset, SkillSettings
from optimiser.fights import Fight, read_fights, tally_trials
from optimiser.paths import HOST_RESULTS, LAST_SIM
from webui.forms.sims import SlotAsk
from webui.service import views
from webui.service.skills import slot_labels
from webui.sims import Running


@dataclass(frozen=True)
class SkillOption:
    """An active skill auto can be told how to use: where it sits (A1, A2 …), its cooldown."""

    id: int
    slot: str
    name: str
    cooldown: int


@dataclass(frozen=True)
class FormSkills:
    role: str  # the form's (a mythical has two: Attack, Defense …)
    skills: tuple[SkillOption, ...]


@dataclass(frozen=True)
class WaveSettings:
    """A wave's skill settings, as the game keeps them: `priorities` by skill id, the game's
    names (Default, First, Second, Third, NotUsed; a skill left out is Default), `openers` the
    skills used first, in order."""

    openers: tuple[int, ...]
    priorities: dict[str, str]


@dataclass(frozen=True)
class SlotView:
    champion: views.ChampionRow
    forms: tuple[FormSkills, ...]
    waves: tuple[WaveSettings, ...]  # one per wave (the game's sequences)


@dataclass(frozen=True)
class TeamOption:
    id: int
    name: str
    area: str  # the game's preset type: ArtifactDungeons, Chimera, …
    slots: tuple[SlotView, ...]


@dataclass(frozen=True)
class SimProgress:
    """The sim under way: building the team's slots (`fighting` False), then its fights done
    (each writes its result as it ends), then summing their results up (`summing`), and the
    seconds since it started."""

    running: bool
    fighting: bool
    summing: bool
    done: int
    total: int
    elapsed: float


@dataclass(frozen=True)
class ChampionResult:
    """A champion's result-screen rows, averaged over the fights."""

    name: str
    dealt: int
    taken: int
    healed: int


@dataclass(frozen=True)
class Uncleared:
    seed: int
    ending: str  # "team defeated", "turn limit", …
    turns: int


@dataclass(frozen=True)
class TrialRow:
    """A Chimera trial completed in some of the fights."""

    name: str  # "Lion Tail Easy"
    completed: int
    boss_turn: int  # the boss's turn it was completed on, on average


@dataclass(frozen=True)
class SimResult:
    """`turns_*` are the battle's turns (the result screen's), over the clears only. Against a
    boss that can't die (`unkillable`: the Chimera, the co-op boss), a fight is cleared when the
    team lasts to the turn limit."""

    title: str  # the stage, as the target picker names it
    team: str
    fights: int
    unkillable: bool
    cleared: int
    turns_mean: float | None
    turns_min: int | None
    turns_max: int | None
    damage_mean: int
    damage_min: int
    damage_max: int
    uncleared: tuple[Uncleared, ...]
    champions: tuple[ChampionResult, ...]
    trials: tuple[TrialRow, ...]  # the Chimera's, completed at least once
    trials_count: int  # every trial the fight has (27 for the Chimera; 0 elsewhere)
    trials_mean: float  # trials completed a fight, on average


@dataclass(frozen=True)
class SimPage:
    teams: tuple[TeamOption, ...]
    team: int | None  # the saved team picked
    seeds: int
    result: SimResult | None  # the last sim run
    running: bool  # a sim under way (the page picks its progress up again after a reload)


def sim_page(account: Account, team: int | None, seeds: int, running: bool) -> SimPage:
    return SimPage(team_options(account), team, seeds, last_result(), running)


def slot_view(account: Account, champion: Champion, waves: tuple[SkillSettings, ...]) -> SlotView:
    return SlotView(
        views.champion_row(champion),
        form_skills(account, champion),
        tuple(
            WaveSettings(wave.openers, {str(k): v for k, v in wave.priorities.items()})
            for wave in waves
        ),
    )


def sim_progress(running: Running | None) -> SimProgress:
    """From the host's results directory: emptied as the fighting starts (until then it holds
    the last sim's), then a file per fight."""
    if running is None:
        return SimProgress(False, False, False, 0, 0, 0.0)

    elapsed = time.time() - running.started
    fighting = HOST_RESULTS.exists() and HOST_RESULTS.stat().st_mtime >= running.started
    done = len(list(HOST_RESULTS.glob("result-*.json"))) if fighting else 0
    return SimProgress(True, fighting, running.summing, done, running.seeds, round(elapsed, 1))


def record_result(title: str, team: str) -> None:
    """The host's results, just written by the page's sim, summed up for the page."""
    LAST_SIM.write_text(json.dumps(asdict(result_view(title, team, read_fights(HOST_RESULTS)))))


def team_label(account: Account, preset_id: int | None, slots: tuple[SlotAsk, ...]) -> str:
    """The saved team's name; "…, edited" once the page has changed it."""
    if preset_id is None or (preset := account.preset(preset_id)) is None:
        return "A team"

    as_saved = tuple(
        SlotAsk(i, saved_settings(preset, i)) for i in preset.champion_ids if i in account.champions
    )
    return preset.name if slots == as_saved else f"{preset.name}, edited"


def team_options(account: Account) -> tuple[TeamOption, ...]:
    """Every saved team with champions, by area then name."""
    return tuple(
        TeamOption(
            preset.id,
            preset.name,
            preset.area,
            tuple(
                slot_view(account, account.champions[i], saved_settings(preset, i))
                for i in preset.champion_ids
                if i in account.champions
            ),
        )
        for preset in sorted(account.presets, key=lambda p: (p.area, p.name, p.id))
        if preset.champion_ids
    )


def saved_settings(preset: Preset, champion_id: int) -> tuple[SkillSettings, ...]:
    """A champion's settings in a saved team, a wave each; none saved: auto's defaults."""
    return preset.skill_settings.get(champion_id) or (SkillSettings({}),)


def form_skills(account: Account, champion: Champion) -> tuple[FormSkills, ...]:
    """Each form's active skills, in slot order (passives have no settings, nor the variants
    of a skill the game swaps in itself, `copy_of`)."""
    tables = account.tables
    forms = tables.hero_forms.get(champion.type_id) or ()

    def form(role: str, skill_ids: tuple[int, ...], slots: dict[int, str]) -> FormSkills:
        actives = (
            SkillOption(i, slots[i], skill.name, skill.cooldown_at(champion.skill_levels.get(i, 1)))
            for i in skill_ids
            if (skill := tables.skills.get(i)) and skill.group == "Active" and not skill.copy_of
        )
        return FormSkills(role, tuple(actives))

    return tuple(form(f.role, f.skills, slot_labels(f, tables)) for f in forms)


def last_result() -> SimResult | None:
    """The page's last sim, as `record_result` kept it (none yet, or kept by an older page:
    None)."""
    if not LAST_SIM.exists():
        return None

    kept = json.loads(LAST_SIM.read_text())

    try:
        return SimResult(
            **{
                **kept,
                "uncleared": tuple(Uncleared(**f) for f in kept["uncleared"]),
                "champions": tuple(ChampionResult(**row) for row in kept["champions"]),
                "trials": tuple(TrialRow(**row) for row in kept["trials"]),
            }
        )
    except (KeyError, TypeError):
        return None


def result_view(title: str, team: str, fights: list[Fight]) -> SimResult:
    won = [f.turns for f in fights if f.cleared]
    names = [c.name for c in fights[0].champions]
    trials = tally_trials(fights) if fights[0].trials else []

    def mean_of(index: int, field: str) -> int:
        return round(statistics.mean(getattr(f.champions[index], field) for f in fights))

    return SimResult(
        title=title,
        team=team,
        fights=len(fights),
        unkillable=fights[0].unkillable,
        cleared=len(won),
        turns_mean=round(statistics.mean(won), 1) if won else None,
        turns_min=min(won) if won else None,
        turns_max=max(won) if won else None,
        damage_mean=round(statistics.mean(f.damage for f in fights)),
        damage_min=min(f.damage for f in fights),
        damage_max=max(f.damage for f in fights),
        uncleared=tuple(Uncleared(f.seed, f.ending, f.turns) for f in fights if not f.cleared),
        champions=tuple(
            ChampionResult(name, mean_of(i, "dealt"), mean_of(i, "taken"), mean_of(i, "healed"))
            for i, name in enumerate(names)
        ),
        trials=tuple(
            TrialRow(t.name, t.completed, round(t.boss_turn))
            for t in trials
            if t.boss_turn is not None
        ),
        trials_count=len(trials),
        trials_mean=round(
            statistics.mean(sum(t is not None for t in f.trials.values()) for f in fights), 1
        ),
    )
