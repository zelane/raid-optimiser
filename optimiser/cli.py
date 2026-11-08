"""
cli.py - `python -m optimiser`: a champion's best builds, from the latest capture.

    uv run python -m optimiser "Anaxia the Reborn" --min SPD=250 --min ACC=200 \\
        --set Lethal=4 --set "Stone Skin=4" --rank HP,DEF,SPD --builds 3

C.RATE and C.DMG limits are in % (`--min CR=100`). Stats: HP ATK DEF SPD RES ACC CR CD.
`DMG` in `--rank` ranks the crit-hit damage of `--skill` (name) against `--enemy-def`.

- `ROOT`, `SLOT_ORDER`: where the data lives, and the order pieces print in
- `main`, `parse_args`: the entry point
- `parse_request`, `parse_pool_arg`, `find_champion`, `parse_limits`, `parse_set_minimums`,
  `parse_ranking`, `parse_damage`, `parse_stat`: the boundary, words into a `Request`
- `print_builds`, `print_shortfall`: the report
- `stat_header`, `stat_row`, `describe`, `normalise`: what the report and boundary share
"""

import argparse
import re
import sys
from pathlib import Path

from optimiser.account import Account, Artifact, Champion, Slot, Stat, Stats, load_account
from optimiser.damage import DamageGoal, Unsupported, damage_goal, estimate_damage
from optimiser.labels import (
    PERCENT_STATS,
    STAT_LABELS,
    format_line,
    format_stat,
    parse_pool,
    pool_label,
)
from optimiser.solve import Build, Goal, Pool, Request, Shortfall, find_builds
from optimiser.stats import build_stats, set_multiplier
from optimiser.store import LOCK_LEVELS, read_locks

ROOT = Path(__file__).resolve().parents[1]
SLOT_ORDER = list(Slot)


def main() -> None:
    args = parse_args(sys.argv[1:])
    account = load_account(args.captures, args.static, args.schema)
    request = parse_request(args, account)

    match find_builds(account, request):
        case Shortfall() as shortfall:
            print_shortfall(shortfall, request)
            sys.exit(1)

        case builds:
            print_builds(builds, request, account)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="optimiser", description="A champion's best builds, from the latest capture."
    )
    parser.add_argument("champion", help='name, or "#<id>" for a particular copy')
    parser.add_argument("--min", action="append", default=[], metavar="STAT=N")
    parser.add_argument("--max", action="append", default=[], metavar="STAT=N")
    parser.add_argument("--set", action="append", default=[], metavar="SET=PIECES")
    parser.add_argument("--rank", required=True, metavar="STAT,STAT,...", help="DMG: damage")
    parser.add_argument("--skill", help="the skill whose damage DMG ranks")
    parser.add_argument("--enemy-def", type=float, default=6000)
    parser.add_argument("--slack", type=float, default=0.01, help="default 0.01 (1%%)")
    parser.add_argument("--builds", type=int, default=3)
    parser.add_argument(
        "--above-level", type=int, default=8, help="only pieces past this level (default 8)"
    )
    parser.add_argument(
        "--pool",
        default="all",
        help="all: any artifact (default); free: unworn, or the champion's own; lock-N: also"
        " gear on champions locked at N or below (lock-0: unlocked champions)",
    )
    parser.add_argument("--captures", type=Path, default=ROOT / "captures" / "latest")
    parser.add_argument("--static", type=Path, default=ROOT / "static")
    parser.add_argument("--schema", type=Path, default=ROOT / "schema" / "schema.json")
    parser.add_argument("--store", type=Path, default=ROOT / "state" / "optimiser.sqlite")
    return parser.parse_args(argv)


def parse_request(args: argparse.Namespace, account: Account) -> Request:
    """Exits with a message on anything that doesn't name a champion, stat or set."""
    champion = find_champion(args.champion, account)
    return Request(
        champion=champion,
        minimums=parse_limits(args.min),
        maximums=parse_limits(args.max),
        set_minimums=parse_set_minimums(args.set, account),
        ranking=parse_ranking(args, champion, account),
        slack=args.slack,
        builds=args.builds,
        pool=parse_pool_arg(args.pool, args.store),
        above_level=args.above_level,
    )


def parse_pool_arg(name: str, store: Path) -> Pool:
    if (pool := parse_pool(name, read_locks(store))) is not None:
        return pool

    sys.exit(f"unknown pool {name!r}: all, free or lock-0 to lock-{max(LOCK_LEVELS)}")


def find_champion(wanted: str, account: Account) -> Champion:
    """By id, or by name: the most developed copy when there are several."""
    if wanted.startswith("#"):
        if champion := account.champions.get(int(wanted[1:])):
            return champion

        sys.exit(f"no champion with id {wanted[1:]}")

    copies = [c for c in account.champions.values() if normalise(c.name) == normalise(wanted)]
    if not copies:
        sys.exit(f"no champion named {wanted!r}")

    best = max(copies, key=lambda c: (c.grade, c.level, c.type_id % 10, c.awakening, c.empower))

    if len(copies) > 1:
        others = ", ".join(f"#{c.id}" for c in copies if c is not best)
        print(f"{len(copies)} copies of {best.name}: using #{best.id} (others: {others})")

    return best


def parse_limits(limits: list[str]) -> Stats:
    parsed: Stats = {}

    for limit in limits:
        name, _, amount = limit.partition("=")
        stat = parse_stat(name)
        value = float(amount)
        parsed[stat] = value / 100 if stat in PERCENT_STATS else value

    return parsed


def parse_set_minimums(sets: list[str], account: Account) -> dict[int, int]:
    by_name = {normalise(s.name): set_id for set_id, s in account.tables.sets.items()}
    minimums: dict[int, int] = {}

    for wanted in sets:
        name, _, pieces = wanted.rpartition("=")
        if (set_id := by_name.get(normalise(name))) is None:
            sys.exit(f"no artifact set named {name!r}")

        minimums[set_id] = int(pieces)

    return minimums


def parse_ranking(
    args: argparse.Namespace, champion: Champion, account: Account
) -> tuple[Goal, ...]:
    names = [name for name in args.rank.split(",") if name.strip()]
    if not names:
        sys.exit("--rank needs at least one stat")

    return tuple(
        parse_damage(args, champion, account) if normalise(name) == "dmg" else parse_stat(name)
        for name in names
    )


def parse_damage(args: argparse.Namespace, champion: Champion, account: Account) -> DamageGoal:
    skills = [
        account.tables.skills[s] for s in account.tables.hero_skills.get(champion.type_id, ())
    ]
    skill = next(
        (s for s in skills if args.skill and normalise(s.name) == normalise(args.skill)), None
    )

    if skill is None:
        sys.exit(f"--skill must name one of: {', '.join(s.name for s in skills)}")

    match damage_goal(skill, champion, args.enemy_def):
        case Unsupported(reason=reason):
            sys.exit(f"can't rank {skill.name}'s damage: {reason}")

        case goal:
            return goal


def parse_stat(name: str) -> Stat:
    key = normalise(name)
    aliases = {normalise(label): stat for stat, label in STAT_LABELS.items()}
    by_name = {normalise(stat.name): stat for stat in Stat} | aliases

    if (stat := by_name.get(key)) is None:
        sys.exit(f"unknown stat {name!r}; use one of {' '.join(s.name for s in Stat)}")

    return stat


def print_builds(builds: list[Build], request: Request, account: Account) -> None:
    champion = request.champion
    tables = account.tables
    worn = [a for a in account.artifacts if a.id in set(champion.artifact_ids)]
    lore = " Lore of Steel," if set_multiplier(champion, tables) > 1 else ""

    print(
        f"{champion.name} #{champion.id}: {champion.rarity} {champion.grade}* L{champion.level},"
        f"{lore} pool: {pool_label(request.pool)}"
    )
    goal = next((g for g in request.ranking if isinstance(g, DamageGoal)), None)
    current = build_stats(champion, worn, tables)
    damage = (lambda stats, gear: estimate_damage(goal, stats, gear, tables.sets)) if goal else None

    print(stat_header() + (f"{'DMG':>9}" if goal else ""))
    print(stat_row("current", current) + (f"{damage(current, worn):>9,.0f}" if damage else ""))

    for number, build in enumerate(builds, 1):
        dmg = f"{damage(build.stats, build.artifacts):>9,.0f}" if damage else ""
        print(stat_row(f"build {number}", build.stats) + dmg)

    if goal:
        print(f"DMG: {goal.skill_name} crit hit vs {goal.enemy_defence:g} DEF")

    for number, build in enumerate(builds, 1):
        print(f"\nbuild {number}")

        for artifact in sorted(build.artifacts, key=lambda a: SLOT_ORDER.index(a.slot)):
            print("  " + describe(artifact, account, champion))


def print_shortfall(shortfall: Shortfall, request: Request) -> None:
    print(f"No build for {request.champion.name} meets the request.")

    if shortfall.reason:
        print(f"  {shortfall.reason}")
        return

    for stat, best in shortfall.highest.items():
        wanted = request.minimums[stat]
        mark = "  <- short" if best < wanted else ""
        print(
            f"  {STAT_LABELS[stat]} at least {format_stat(stat, wanted)}: "
            f"best possible {format_stat(stat, best)}{mark}"
        )

    for stat, lowest in shortfall.lowest.items():
        wanted = request.maximums[stat]
        mark = "  <- over" if lowest > wanted else ""
        print(
            f"  {STAT_LABELS[stat]} at most {format_stat(stat, wanted)}: "
            f"lowest possible {format_stat(stat, lowest)}{mark}"
        )

    print("  (each on its own; together they may still conflict)")


def stat_header() -> str:
    return f"{'':10}" + "".join(f"{label:>8}" for label in STAT_LABELS.values())


def stat_row(label: str, stats: Stats) -> str:
    return f"{label:10}" + "".join(f"{format_stat(stat, stats[stat]):>8}" for stat in STAT_LABELS)


def describe(artifact: Artifact, account: Account, champion: Champion) -> str:
    """One line per piece: slot, set, rank and level, main stat, and who wears it now."""
    artifact_set = account.tables.sets.get(artifact.set_id)
    set_name = artifact_set.name if artifact_set else "no set"
    owner_id = account.owners.get(artifact.id)
    owner = "" if owner_id in (None, champion.id) else f"  (on {account.champions[owner_id].name})"
    return (
        f"{artifact.slot.value:7} {set_name:14} {artifact.rank}* L{artifact.level:<3}"
        f"{format_line(artifact.primary)}  #{artifact.id}{owner}"
    )


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())
