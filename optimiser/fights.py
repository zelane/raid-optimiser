"""
fights.py - fights the game's own battle engine played (`host/`, `just fight`), read from its
`BattleResult`s (the game's JSON) and summed up as its result screen shows them: per champion,
damage dealt to the enemy, damage taken and HP healed; and how many turns the boss had.

Each effect's row (`TurnStatistics`: producer `z`, target `x`, `DamageDealt` `d`,
`RestoredHp` `h`) is counted once, in its producer's statistics: rows can be alike (two
Poisons ticking together), so they can't be told apart by their values. `d` is what the boss
took in full: it can't die, and a run's damage carries on past its HP.

A fight is cleared when it's won, or, against a boss the game won't let die (`BossData.
IsUnkillable`: the Chimera, the co-op boss), when the team lasts to the turn limit: the game
calls that a defeat too, its `FinishCause` telling them apart.

- `ENEMY`: the enemy side's owner id
- `OUTCOMES`, `FINISHES`: the game's `BattleResultType` and `BattleFinishCause`
- `Tally`, `Fight`: one champion's rows, one fight
- `read_fights`, `read_fight`: result files, in seed order
- `TrialTally`, `tally_trials`: how often each Chimera trial was completed over the fights
- `print_report`: a run of seeds summed up (`main`)
- `differences`: a replay against the fight the game recorded (`main --against`)
"""

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from optimiser.enemies import load_enemies
from optimiser.paths import GAME

ENEMY = -1


@dataclass(frozen=True)
class Tally:
    name: str
    dealt: int
    taken: int
    healed: int


OUTCOMES = {1: "Victory", 2: "Defeat", 3: "Draw"}
FINISHES = {
    0: "OneOfTheTeamDefeated",
    1: "Retreat",
    2: "TurnsLimitReached",
    3: "PrematureResult",
    4: "TimeLimitReached",
    5: "UserConnectionTimeout",
    6: "BothTeamsDefeated",
}


@dataclass(frozen=True)
class Fight:
    """`turns`: the battle's (`BattleState.CurrentTurn`), everyone's; `team_turns` the
    player's (`PlayerTurnCount`)."""

    seed: int  # 0: the setup's own
    champions: tuple[Tally, ...]
    boss_turns: int
    outcome: str
    finish: str  # why it ended (FINISHES); "" in results read before the reader read it
    unkillable: bool  # against a boss that can't die
    turns: int
    team_turns: int
    # The Chimera's trials (`BattleHero.Challenges`, by trial skill id): the boss's turn each was
    # completed on (`SelfTurnWhichCompleted`), None if it wasn't; empty for other fights
    trials: dict[int, int | None] = field(default_factory=dict)

    @property
    def damage(self) -> int:
        return sum(c.dealt for c in self.champions)

    @property
    def cleared(self) -> bool:
        if self.unkillable:
            return self.finish == "TurnsLimitReached"

        return self.outcome == "Victory"

    @property
    def ending(self) -> str:
        """How a fight not cleared ended, in a word or two."""
        match self.finish:
            case "OneOfTheTeamDefeated" | "BothTeamsDefeated":
                return "team defeated"
            case "TurnsLimitReached":
                return "turn limit"
            case "Retreat":
                return "stopped"
            case "":
                return self.outcome.lower()
            case other:
                return other


@dataclass(frozen=True)
class HeroTypes:
    """What a fight's heroes are, by type id: names, and the bosses that can't die."""

    names: dict[int, str]
    unkillable: frozenset[int]


def load_hero_types() -> HeroTypes:
    names = {h["id"]: h["name"] for h in json.loads((GAME / "hero_types.json").read_text())}
    unkillable = frozenset(i for i, t in load_enemies(GAME).types.items() if t.unkillable)
    return HeroTypes(names, unkillable)


def read_fights(results: Path) -> list[Fight]:
    types = load_hero_types()
    paths = sorted(results.glob("result-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return [read_fight(path, types, int(path.stem.split("-")[1])) for path in paths]


def read_fight(path: Path, types: HeroTypes, seed: int = 0) -> Fight:
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

    champions = tuple(
        Tally(types.names.get(hero["t"], str(hero["t"])), dealt[i], taken[i], healed[i])
        for i, hero in sorted(heroes.items())
        if i not in enemy
    )
    state = result.get("s", {})

    return Fight(
        seed=seed,
        champions=champions,
        boss_turns=sum(r.get("t", 0) for r in heroes[min(enemy)]["r"].values()) if enemy else 0,
        outcome=OUTCOMES.get(result.get("i", 0), str(result.get("i"))),
        finish=FINISHES.get(result["c"], str(result["c"])) if "c" in result else "",
        unkillable=any(heroes[i]["t"] in types.unkillable for i in enemy),
        turns=state.get("t", 0),
        team_turns=state.get("pt", 0),
        trials=trials_of(state),
    )


def trials_of(state: dict) -> dict[int, int | None]:
    """The enemy side's trials in the battle's final state (the Chimera's: `ch` on the boss)."""
    enemies = (state.get("s") or {}).get("h") or []
    return {int(i): t.get("t") for hero in enemies for i, t in (hero.get("ch") or {}).items()}


def rows_of(hero: dict) -> list[dict]:
    """A hero's rows, every round's turns'; the game's JSON leaves out a round's `r` when the
    hero took no turn in it (a Hydra head grown again)."""
    return [row for rnd in hero["r"].values() for rows in rnd.get("r", {}).values() for row in rows]


@dataclass(frozen=True)
class TrialTally:
    skill: int
    name: str  # form, part and level: "Lion Tail Easy"
    completed: int  # fights it was completed in
    boss_turn: float | None  # the boss's turn it was completed on, on average


def tally_trials(fights: list[Fight]) -> list[TrialTally]:
    """Every trial the fights had, in the game's order (by skill id: form, part, level)."""
    names = {
        t.skill: f"{t.form} {t.part} {t.level}"
        for tier in load_enemies(GAME).chimera.tiers
        for t in tier.trials
    }
    tallies = []

    for skill in sorted(fights[0].trials):
        turns = [t for f in fights if (t := f.trials.get(skill)) is not None]
        mean = statistics.mean(turns) if turns else None
        tallies.append(TrialTally(skill, names.get(skill, str(skill)), len(turns), mean))

    return tallies


def print_report(fights: list[Fight]) -> None:
    damage = sorted(f.damage for f in fights)
    own = fights[0]
    print(f"{len(fights)} fights (seed 0: the setup's own, {own.outcome}, {own.damage:,} dealt)")
    print_outcomes(fights)
    print_trials(fights)

    if len(fights) > 1:
        deciles = statistics.quantiles(damage, n=10)
        mean, median = statistics.mean(damage) / 1e6, statistics.median(damage) / 1e6
        print(f"  damage: {mean:.1f}M on average, median {median:.1f}M")
        print(f"    9 in 10 over {deciles[0] / 1e6:.1f}M, 1 in 10 over {deciles[-1] / 1e6:.1f}M")
        turns = [f.boss_turns for f in fights]

        if all(turns):  # a boss counting its turns in every fight (the co-op boss's World-Killer)
            print(f"  boss turns: {statistics.mean(turns):.1f} ({min(turns)} to {max(turns)})")

    print(f"  {'':24} {'dealt':>13} {'taken':>10} {'healed':>11}   (seed 0 | average)")

    for i, champion in enumerate(own.champions):
        average = statistics.mean(f.champions[i].dealt for f in fights)
        rows = f"{champion.dealt:>13,} {champion.taken:>10,} {champion.healed:>11,}"
        print(f"  {champion.name:24} {rows}   {average:>13,.0f}")


def print_outcomes(fights: list[Fight]) -> None:
    """How often it's cleared, and the turns a clear takes (everyone's, and the team's own)."""
    won = [f for f in fights if f.cleared]
    lost = [f for f in fights if not f.cleared]
    cleared = "lasted to the turn limit" if fights[0].unkillable else "cleared"
    print(f"  {cleared} {len(won)} of {len(fights)} ({len(won) / len(fights):.1%})")

    if lost:
        shown = ", ".join(f"{f.seed} ({f.ending}, {f.turns} turns)" for f in lost[:12])
        print(f"    not cleared, by seed: {shown}{' …' if len(lost) > 12 else ''}")

    for label, turns in (
        ("turns", [f.turns for f in won]),
        ("team turns", [f.team_turns for f in won]),
    ):
        if turns:
            spread = f"{min(turns)} to {max(turns)}"
            print(f"    {label}: {statistics.mean(turns):.1f} on average ({spread})")


def print_trials(fights: list[Fight]) -> None:
    """How often each Chimera trial was completed, by form, part and level, with the boss's
    turn it took on average."""
    if not fights[0].trials:
        return

    print("  trials completed:")

    for trial in tally_trials(fights):
        if trial.boss_turn is not None:
            when = f", boss turn {trial.boss_turn:.0f} on average"
            print(f"    {trial.name:24} {trial.completed:>4} of {len(fights)}{when}")

    done = [sum(t is not None for t in f.trials.values()) for f in fights]
    print(f"    per fight: {statistics.mean(done):.1f} of {len(fights[0].trials)} on average")


def differences(sim: Fight, real: Fight) -> list[str]:
    """Where a replay differs from the fight the game recorded: outcome, turns, each
    champion's rows (the result screen's), in the same order, and the trials. What the game's
    record lacks isn't compared: it can come without statistics (one quick battle's did), and
    the reader leaves out trials whose objects the game has reused."""
    found = [
        f"{what}: game {theirs}, replay {ours}"
        for what, ours, theirs in (
            ("outcome", sim.outcome, real.outcome),
            ("ending", sim.finish, real.finish or sim.finish),
            ("turns", sim.turns, real.turns),
            ("team turns", sim.team_turns, real.team_turns),
        )
        if ours != theirs
    ]

    for ours, theirs in zip(sim.champions, real.champions or sim.champions, strict=True):
        for what in ("dealt", "taken", "healed"):
            if getattr(ours, what) != getattr(theirs, what):
                game, replay = getattr(theirs, what), getattr(ours, what)
                found.append(f"{ours.name} {what}: game {game:,}, replay {replay:,}")

    for skill, turn in real.trials.items():
        if sim.trials.get(skill) != turn:
            found.append(f"trial {skill} completed: game {turn}, replay {sim.trials.get(skill)}")

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

    real = read_fight(args.against, load_hero_types())
    found = differences(fights[0], real)
    print(
        f"the replay matches the game's fight: {real.outcome}, {real.turns} turns"
        if not found
        else f"{len(found)} differences from the game's fight:"
    )

    if not real.champions:
        print("  (the game's record has no rows: not compared)")

    for line in found:
        print(f"  {line}")


if __name__ == "__main__":
    main()
