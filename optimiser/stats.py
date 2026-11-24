"""
stats.py - a champion's stats as the game adds them up: base stats (rank, level and
ascension), then fixed bonuses, gear and set bonuses, and what a battle adds (`battle`: buffs,
an aura). Percentages apply to base stats, except crit, where they add.

Everything but gear is a constant per champion, and gear adds linearly per piece, which is
what lets the solver treat a build as a sum.

- `ADDITIVE`: the stats whose percentages add rather than scale
- `build_stats`: a champion's stats in a given set of artifacts
- `base_stats`, `constant_stats`, `artifact_stats`, `set_stats`, `set_multiplier`: its parts
- `scaled`, `level_bonuses`, `resolve`, `add`: what the parts share
"""

from collections import Counter
from collections.abc import Iterable

from optimiser import levels
from optimiser.account import (
    Artifact,
    ArtifactSet,
    Bonus,
    Champion,
    FixedSet,
    Stat,
    Stats,
    Tables,
    VariableSet,
)

ADDITIVE = (Stat.CR, Stat.CD)


def build_stats(
    champion: Champion,
    artifacts: Iterable[Artifact],
    tables: Tables,
    battle: tuple[Bonus, ...] = (),
) -> Stats:
    """The stats the game shows for `champion` wearing `artifacts` (in a battle, with what
    `battle` adds)."""
    base = base_stats(champion, tables)
    worn = list(artifacts)
    pieces = Counter(a.set_id for a in worn)
    multiplier = set_multiplier(champion, tables)

    return add(
        constant_stats(champion, tables, battle),
        *(artifact_stats(a, base) for a in worn),
        *(
            set_stats(tables.sets[set_id], count, base, multiplier)
            for set_id, count in pieces.items()
            if set_id in tables.sets
        ),
    )


def base_stats(champion: Champion, tables: Tables) -> Stats:
    """The form's at the champion's rank and level, as the game scales them."""
    return levels.base_stats(tables.form_of(champion).unscaled, champion.grade, champion.level)


def constant_stats(champion: Champion, tables: Tables, battle: tuple[Bonus, ...] = ()) -> Stats:
    """Base stats plus everything that doesn't depend on gear: the account's Great Hall, the
    arena league, awakening, empowerment, stat masteries, relics and `battle`."""
    base = base_stats(champion, tables)
    fixed = [
        *champion.great_hall,
        *tables.arena,
        *level_bonuses(tables.awakening, champion.rarity, champion.awakening),
        *level_bonuses(tables.empower, champion.rarity, champion.empower),
        *(tables.masteries[m] for m in champion.masteries if m in tables.masteries),
        *champion.relics,
        *battle,
    ]
    return add(base, *({bonus.stat: resolve(bonus, base)} for bonus in fixed))


def artifact_stats(artifact: Artifact, base: Stats) -> Stats:
    bonuses = [bonus for line in artifact.lines() if (bonus := line.bonus())]
    return add(*({b.stat: resolve(b, base)} for b in bonuses))


def set_stats(artifact_set: ArtifactSet, count: int, base: Stats, multiplier: float) -> Stats:
    """What `count` pieces of a set add."""
    match artifact_set:
        case FixedSet(pieces=pieces, bonuses=bonuses):
            return scaled(bonuses, base, multiplier * (count // pieces))

        case VariableSet(totals=totals):
            reached = [pieces for pieces in totals if pieces <= count]
            return scaled(totals[max(reached)] if reached else (), base, multiplier)


def scaled(bonuses: tuple[Bonus, ...], base: Stats, factor: float) -> Stats:
    return add(*({b.stat: resolve(b, base) * factor} for b in bonuses))


def set_multiplier(champion: Champion, tables: Tables) -> float:
    """Lore of Steel scales set stat bonuses, for champions who have it."""
    lore = tables.lore_of_steel
    return lore.multiplier if lore.mastery_id in champion.masteries else 1.0


def level_bonuses(
    table: dict[str, list[tuple[Bonus, ...]]], rarity: str, level: int
) -> tuple[Bonus, ...]:
    """The cumulative bonuses at `level` (0: none) for the rarity, if it has the table."""
    levels = table.get(rarity, [])
    return levels[level - 1] if 0 < level <= len(levels) else ()


def resolve(bonus: Bonus, base: Stats) -> float:
    """A bonus as an amount of its stat."""
    if bonus.absolute or bonus.stat in ADDITIVE:
        return bonus.value

    return bonus.value * base[bonus.stat]


def add(*parts: Stats) -> Stats:
    return {stat: sum(part.get(stat, 0) for part in parts) for stat in Stat}
