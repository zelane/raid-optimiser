"""
sims.py - the sim page: one of the account's saved teams against a stage, fought many times on
the game's own battle engine (the battle host, `webui.sims` runs it), and the last sim's
results: how often it cleared, the turns a win took, the damage, and each champion's
result-screen rows on average.

- `TeamOption`, `ChampionRow`, `SimResult`, `SimPage`: the views
- `sim_page`: the page
- `team_options`, `last_result`, `result_view`: its parts
"""

import json
import statistics
from dataclasses import dataclass

from optimiser.account import Account
from optimiser.fights import Fight, read_fights
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
class SimResult:
    """`turns_*` are the battle's turns (the result screen's), over the wins only."""

    title: str  # the stage, as the target picker names it
    team: str
    fights: int
    cleared: int
    turns_mean: float | None
    turns_min: int | None
    turns_max: int | None
    damage_mean: int
    lost_seeds: tuple[int, ...]
    champions: tuple[ChampionRow, ...]


@dataclass(frozen=True)
class SimPage:
    teams: tuple[TeamOption, ...]
    team: int | None  # the saved team picked
    seeds: int
    result: SimResult | None  # the last sim run


def sim_page(account: Account, team: int | None, seeds: int) -> SimPage:
    return SimPage(team_options(account), team, seeds, last_result(account))


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


def last_result(account: Account) -> SimResult | None:
    """The last sim's fights (none run yet: None)."""
    if not LAST_SIM.exists() or not HOST_RESULTS.exists():
        return None

    fights = read_fights(HOST_RESULTS)

    if not fights:
        return None

    sim = json.loads(LAST_SIM.read_text())
    preset = account.preset(sim["preset"])
    return result_view(sim["title"], preset.name if preset else f"team {sim['preset']}", fights)


def result_view(title: str, team: str, fights: list[Fight]) -> SimResult:
    won = [f.turns for f in fights if f.outcome == "Victory"]
    names = [c.name for c in fights[0].champions]

    def mean_of(index: int, field: str) -> int:
        return round(statistics.mean(getattr(f.champions[index], field) for f in fights))

    return SimResult(
        title=title,
        team=team,
        fights=len(fights),
        cleared=len(won),
        turns_mean=round(statistics.mean(won), 1) if won else None,
        turns_min=min(won) if won else None,
        turns_max=max(won) if won else None,
        damage_mean=round(statistics.mean(f.damage for f in fights)),
        lost_seeds=tuple(f.seed for f in fights if f.outcome != "Victory"),
        champions=tuple(
            ChampionRow(name, mean_of(i, "dealt"), mean_of(i, "taken"), mean_of(i, "healed"))
            for i, name in enumerate(names)
        ),
    )
