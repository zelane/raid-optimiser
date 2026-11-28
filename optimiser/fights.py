"""
fights.py - fights the game's own battle engine played (`host/`, `just fight`), read from its
`BattleResult`s (the game's JSON) and summed up as its result screen shows them: per champion,
damage dealt to the enemy, damage taken and HP healed; and how many turns the boss had.

Each effect's row (`TurnStatistics`: producer `z`, target `x`, `DamageDealt` `d`,
`RestoredHp` `h`) is counted once, in its producer's statistics: rows can be alike (two
Poisons ticking together), so they can't be told apart by their values. `d` is what the boss
took in full: it can't die, and a run's damage carries on past its HP.

- `ENEMY`: the enemy side's owner id
- `Tally`, `Fight`: one champion's rows, one fight
- `read_fights`, `read_fight`: result files, in seed order
- `print_report`: a run of seeds summed up (`main`)
- `differences`: a replay against the fight the game recorded (`main --against`)
"""

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from optimiser.paths import GAME

ENEMY = -1


@dataclass(frozen=True)
class Tally:
    name: str
    dealt: int
    taken: int
    healed: int


OUTCOMES = {1: "Victory", 2: "Defeat", 3: "Draw"}  # BattleResultType


@dataclass(frozen=True)
class Fight:
    """`turns`: the battle's (`BattleState.CurrentTurn`), everyone's; `team_turns` the
    player's (`PlayerTurnCount`)."""

    seed: int  # 0: the setup's own
    champions: tuple[Tally, ...]
    boss_turns: int
    outcome: str
    turns: int
    team_turns: int

    @property
    def damage(self) -> int:
        return sum(c.dealt for c in self.champions)


def read_fights(results: Path) -> list[Fight]:
    names = {h["id"]: h["name"] for h in json.loads((GAME / "hero_types.json").read_text())}
    paths = sorted(results.glob("result-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return [read_fight(path, names, int(path.stem.split("-")[1])) for path in paths]


def read_fight(path: Path, names: dict[int, str], seed: int = 0) -> Fight:
    """A fight's result: the host's (`result-<seed>.json`) or one the game recorded and the
    reader found (`just results`), the same shape."""
    result = json.loads(path.read_text())
    heroes = {int(i): hero for i, hero in result["x"]["d"].items()}
    enemy = {i for i, hero in heroes.items() if hero["o"] == ENEMY}
    dealt, taken, healed = defaultdict(int), defaultdict(int), defaultdict(int)

    for producer, hero in heroes.items():
        for row in rows_of(hero):
            if row.get("z") != producer:
                continue

            target, damage = row.get("x"), row.get("d") or 0

            if producer not in enemy and target in enemy:
                dealt[producer] += damage
            elif producer in enemy and target in heroes and target not in enemy:
                taken[target] += damage

            healed[producer] += row.get("h") or 0

    boss = min(enemy)
    champions = tuple(
        Tally(names.get(hero["t"], str(hero["t"])), dealt[i], taken[i], healed[i])
        for i, hero in sorted(heroes.items())
        if i not in enemy
    )
    state = result.get("s", {})

    return Fight(
        seed=seed,
        champions=champions,
        boss_turns=sum(r.get("t", 0) for r in heroes[boss]["r"].values()),
        outcome=OUTCOMES.get(result.get("i", 0), str(result.get("i"))),
        turns=state.get("t", 0),
        team_turns=state.get("pt", 0),
    )


def rows_of(hero: dict) -> list[dict]:
    return [row for rnd in hero["r"].values() for rows in rnd["r"].values() for row in rows]


def print_report(fights: list[Fight]) -> None:
    damage = sorted(f.damage for f in fights)
    own = fights[0]
    print(f"{len(fights)} fights (seed 0: the setup's own, {own.outcome}, {own.damage:,} dealt)")
    print_outcomes(fights)

    if len(fights) > 1:
        deciles = statistics.quantiles(damage, n=10)
        mean, median = statistics.mean(damage) / 1e6, statistics.median(damage) / 1e6
        print(f"  damage: {mean:.1f}M on average, median {median:.1f}M")
        print(f"    9 in 10 over {deciles[0] / 1e6:.1f}M, 1 in 10 over {deciles[-1] / 1e6:.1f}M")
        turns = [f.boss_turns for f in fights]

        if any(turns):  # a boss fight (the co-op boss's World-Killer counts them)
            print(f"  boss turns: {statistics.mean(turns):.1f} ({min(turns)} to {max(turns)})")

    print(f"  {'':24} {'dealt':>13} {'taken':>10} {'healed':>11}   (seed 0 | average)")

    for i, champion in enumerate(own.champions):
        average = statistics.mean(f.champions[i].dealt for f in fights)
        rows = f"{champion.dealt:>13,} {champion.taken:>10,} {champion.healed:>11,}"
        print(f"  {champion.name:24} {rows}   {average:>13,.0f}")


def print_outcomes(fights: list[Fight]) -> None:
    """How often it's won, and the turns a win takes (everyone's, and the team's own)."""
    won = [f for f in fights if f.outcome == "Victory"]
    lost = [f for f in fights if f.outcome != "Victory"]
    print(f"  cleared {len(won)} of {len(fights)} ({len(won) / len(fights):.1%})")

    if lost:
        shown = ", ".join(f"{f.seed} ({f.outcome.lower()}, {f.turns} turns)" for f in lost[:12])
        print(f"    not cleared, by seed: {shown}{' …' if len(lost) > 12 else ''}")

    for label, turns in (
        ("turns", [f.turns for f in won]),
        ("team turns", [f.team_turns for f in won]),
    ):
        if turns:
            spread = f"{min(turns)} to {max(turns)}"
            print(f"    {label}: {statistics.mean(turns):.1f} on average ({spread})")


def differences(sim: Fight, real: Fight) -> list[str]:
    """Where a replay differs from the fight the game recorded: outcome, turns, and each
    champion's rows (the result screen's), in the same order."""
    found = [
        f"{what}: game {theirs}, replay {ours}"
        for what, ours, theirs in (
            ("outcome", sim.outcome, real.outcome),
            ("turns", sim.turns, real.turns),
            ("team turns", sim.team_turns, real.team_turns),
        )
        if ours != theirs
    ]

    for ours, theirs in zip(sim.champions, real.champions, strict=True):
        for what in ("dealt", "taken", "healed"):
            if getattr(ours, what) != getattr(theirs, what):
                game, replay = getattr(theirs, what), getattr(ours, what)
                found.append(f"{ours.name} {what}: game {game:,}, replay {replay:,}")

    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("results", type=Path, help="the host's result-<seed>.json files")
    parser.add_argument(
        "--against", type=Path, help="a fight the game recorded (just results): compare seed 0"
    )
    args = parser.parse_args()
    fights = read_fights(args.results)

    if args.against is None:
        print_report(fights)
        return

    names = {h["id"]: h["name"] for h in json.loads((GAME / "hero_types.json").read_text())}
    real = read_fight(args.against, names)
    found = differences(fights[0], real)
    print(
        f"the replay matches the game's fight: {real.outcome}, {real.turns} turns"
        if not found
        else f"{len(found)} differences from the game's fight:"
    )

    for line in found:
        print(f"  {line}")


if __name__ == "__main__":
    main()
