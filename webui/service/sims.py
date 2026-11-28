"""
sims.py - the sim page: one of the account's saved teams against a stage, fought many times on
the game's own battle engine (the battle host, `webui.sims` runs it), and the last sim's
results: how often it cleared, the turns a win took, the damage, and each champion's
result-screen rows on average.

- `TeamOption`, `ChampionRow`, `Uncleared`, `TrialRow`, `SimResult`, `SimPage`: the views
- `sim_page`: the page
- `record_result`: a sim just run, summed up and kept (`paths.LAST_SIM`): the page shows it
  whatever the host runs after (`just fight` in a terminal rewrites the host's results)
- `team_options`, `last_result`, `result_view`: its parts
"""

import json
import statistics
from dataclasses import asdict, dataclass

from optimiser.account import Account
from optimiser.fights import Fight, read_fights, tally_trials
from optimiser.paths import HOST_RESULTS, LAST_SIM


@dataclass(frozen=True)
class TeamOption:
    id: int
    name: str
    area: str  # the game's preset type: ArtifactDungeons, Chimera, …
    champions: tuple[str, ...]


@dataclass(frozen=True)
class ChampionRow:
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
    uncleared: tuple[Uncleared, ...]
    champions: tuple[ChampionRow, ...]
    trials: tuple[TrialRow, ...]  # the Chimera's, completed at least once
    trials_count: int  # every trial the fight has (27 for the Chimera; 0 elsewhere)
    trials_mean: float  # trials completed a fight, on average


@dataclass(frozen=True)
class SimPage:
    teams: tuple[TeamOption, ...]
    team: int | None  # the saved team picked
    seeds: int
    result: SimResult | None  # the last sim run


def sim_page(account: Account, team: int | None, seeds: int) -> SimPage:
    return SimPage(team_options(account), team, seeds, last_result())


def record_result(account: Account, preset_id: int, title: str) -> None:
    """The host's results, just written by the page's sim, summed up for the page."""
    preset = account.preset(preset_id)
    team = preset.name if preset else f"team {preset_id}"
    LAST_SIM.write_text(json.dumps(asdict(result_view(title, team, read_fights(HOST_RESULTS)))))


def team_options(account: Account) -> tuple[TeamOption, ...]:
    """Every saved team with champions, by area then name."""
    return tuple(
        TeamOption(
            preset.id,
            preset.name,
            preset.area,
            tuple(account.champions[i].name for i in preset.champion_ids if i in account.champions),
        )
        for preset in sorted(account.presets, key=lambda p: (p.area, p.name, p.id))
        if preset.champion_ids
    )


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
                "champions": tuple(ChampionRow(**row) for row in kept["champions"]),
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
        uncleared=tuple(Uncleared(f.seed, f.ending, f.turns) for f in fights if not f.cleared),
        champions=tuple(
            ChampionRow(name, mean_of(i, "dealt"), mean_of(i, "taken"), mean_of(i, "healed"))
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
