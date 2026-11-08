"""
potential.py - what an accessory could become: every way its remaining upgrades can land
and, if it hasn't been reworked, every way a rework can re-pick it, each scored against the
champion types it could be for (`roles`). A piece's potential is a quantile of
those scores, so concentrated rolls (a triple roll anywhere) count for their upside.

Scores are in average 6★ rolls: each stat's value (flat and % together, flat as a share of a
typical base stat), times the type's weight for it, plus the main stat as `MAIN_ROLLS` rolls
scaled by its rank's top value. Future rolls are average rolls.

Upgrades (at +4, +8, +12, +16) add a substat until there are four, any the slot can roll
that the piece lacks alike, then a roll to one of the four alike. A rework keeps each line's
number of rolls, the set and the faction, and re-picks the main stat and which stat each line
is, alike among what the slot can roll.

- `ROLL_6`, `RANK_ROLL`, `REFERENCE_BASE`, `MAIN_ROLLS`, `UPGRADE_LEVELS`, `ROLL_TO`,
  `MAX_SUBSTATS`, `QUANTILE`, `ACCESSORIES`, `MAIN_STATS`, `SUBSTATS`: the game, and units
- `Scorer`, `make_scorer`: the types, as scoring needs them
- `Scores`, `Potential`: a piece's scores
- `assess`: a piece's potential
- `Line`, `Outcomes`, `ReworkBase`, `Scored`: what the outcomes are worked out from, and are
- `natural`, `reworked` (`count_chances`, `rework_outcomes`): its outcomes, and their scores
  (`score_outcomes`, `quantiles`)
- `roll_size`, `one_roll`, `main_line`, `roll_units`, `line_units`, `main_units`,
  `upgrades_left`: what they share
"""

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations, permutations
from math import comb, factorial

import numpy as np

from optimiser.accessories.roles import ChampionType, Kind, types_for
from optimiser.account import Artifact, GearLine, GearTables, Slot, Stat

ACCESSORIES = (Slot.RING, Slot.AMULET, Slot.BANNER)
MAIN_STATS = {
    Slot.RING: (Stat.ATK, Stat.HP, Stat.DEF),
    Slot.AMULET: (Stat.ATK, Stat.CD, Stat.HP, Stat.DEF),
    Slot.BANNER: (Stat.ATK, Stat.HP, Stat.DEF, Stat.ACC, Stat.RES),
}
BODY_LINES = tuple(
    (s, absolute) for s in (Stat.ATK, Stat.HP, Stat.DEF) for absolute in (True, False)
)
SUBSTATS = {  # each line a slot can roll: (stat, absolute)
    Slot.RING: BODY_LINES,
    Slot.AMULET: (
        (Stat.ATK, True),
        (Stat.HP, True),
        (Stat.DEF, True),
        (Stat.ACC, True),
        (Stat.RES, True),
        (Stat.CD, False),
    ),
    Slot.BANNER: ((Stat.SPD, True), *BODY_LINES),
}

# An average 6★ substat roll (measured on the account's gear): the unit scores count in.
ROLL_6 = {
    (Stat.HP, False): 0.06,
    (Stat.ATK, False): 0.06,
    (Stat.DEF, False): 0.06,
    (Stat.CR, False): 0.06,
    (Stat.CD, False): 0.06,
    (Stat.SPD, True): 5.5,
    (Stat.ACC, True): 10.5,
    (Stat.RES, True): 10.5,
    (Stat.HP, True): 380,
    (Stat.ATK, True): 22.5,
    (Stat.DEF, True): 22.8,
}
RANK_ROLL = {6: 1.0, 5: 0.82}  # a roll's size against 6★; lower ranks scale by stars
REFERENCE_BASE = {Stat.HP: 17010, Stat.ATK: 1035, Stat.DEF: 1035}  # median 6★ L60 base
MAIN_ROLLS = 4  # a 6★ main stat at +16, in rolls of its stat
UPGRADE_LEVELS = (4, 8, 12, 16)
ROLL_TO = 12  # rolling stops here unless a piece is confirmed good
MAX_SUBSTATS = 4
QUANTILE = 0.75

STATS = tuple(Stat)
HP_INDEX, DEF_INDEX = STATS.index(Stat.HP), STATS.index(Stat.DEF)


@dataclass(frozen=True, eq=False)  # hashed by identity: reworks are cached per scorer
class Scorer:
    """The champion types as a (type, stat) weight matrix, and the tables that size main
    stats; `make_scorer` builds one."""

    types: tuple[ChampionType, ...]
    gear: GearTables
    matrix: np.ndarray
    balance: np.ndarray


def make_scorer(types: tuple[ChampionType, ...], gear: GearTables) -> Scorer:
    matrix = np.array([[t.weight(stat) for stat in STATS] for t in types])
    return Scorer(types, gear, matrix, np.array([t.balance for t in types]))


@dataclass(frozen=True)
class Scores:
    """Quantile scores: the best suited type, and the best of each kind (0 if none suits)."""

    best: float
    damage: float
    support: float
    fit: str | None  # the key of the type the best score is for


@dataclass(frozen=True)
class Potential:
    """`now`: as it stands. `at_roll_to`, `natural`: once levelled to +12 and +16.
    `rework`: reworked, then levelled to +16; a piece below +12 is rolled to +12 first (cheaper,
    and it tells more). None if it's been reworked already: that happens only once."""

    now: Scores
    at_roll_to: Scores
    natural: Scores
    rework: Scores | None

    def value(self) -> float:
        return max(self.natural.best, self.rework.best if self.rework else 0)


def assess(artifact: Artifact, scorer: Scorer) -> Potential:
    lines = tuple(
        Line(
            line.stat, line.absolute, line_units(line.stat, line.absolute, line.value + line.glyph)
        )
        for line in artifact.substats
    )
    main = artifact.primary.stat or Stat.HP
    allowed = types_for(artifact.set_id, artifact.slot, main, artifact.faction, scorer.types)
    roll = roll_size(artifact.rank)
    main_rolls = main_units(scorer.gear, artifact.slot, main, artifact.rank)

    def natural_to(level: int) -> Scores:
        upgrades = upgrades_left(artifact.level, level)
        outcomes = natural(artifact.slot, main, lines, upgrades, roll)
        return score_outcomes(outcomes, main, main_rolls, allowed, scorer)

    rework = None

    if not artifact.reworked:
        counts = tuple(line.rolls + 1 for line in artifact.substats)
        rolled_to = max(artifact.level, ROLL_TO)
        chances = count_chances(counts, upgrades_left(artifact.level, rolled_to))
        upgrades = upgrades_left(rolled_to, UPGRADE_LEVELS[-1])
        base = ReworkBase(artifact.slot, artifact.rank, artifact.set_id, artifact.faction)
        rework = reworked(base, chances, upgrades, scorer)

    return Potential(
        now=natural_to(artifact.level),
        at_roll_to=natural_to(max(artifact.level, ROLL_TO)),
        natural=natural_to(UPGRADE_LEVELS[-1]),
        rework=rework,
    )


@dataclass(frozen=True)
class Line:
    """A substat: `stat` None for damage dealt/taken; `units` its value in average rolls."""

    stat: Stat | None
    absolute: bool
    units: float


@dataclass(frozen=True)
class Outcomes:
    """Ways a piece can turn out: each one's chance, and its stat totals (a row per outcome,
    a column per stat)."""

    chances: np.ndarray
    totals: np.ndarray


def natural(
    slot: Slot, main: Stat, lines: tuple[Line, ...], upgrades: int, roll: float
) -> Outcomes:
    """Each way the upgrades can land. New substats come first, any combination alike; the
    rest spread over the four lines multinomially."""
    held = {(line.stat, line.absolute) for line in lines}
    candidates = [c for c in SUBSTATS[slot] if c not in held and c != main_line(main)]
    new_count = min(upgrades, MAX_SUBSTATS - len(lines), len(candidates))
    boosts = upgrades - new_count
    chances: list[float] = []
    totals_by_outcome: list[np.ndarray] = []

    for added in combinations(candidates, new_count):
        all_lines = [*lines, *(Line(stat, absolute, 0.0) for stat, absolute in added)]
        added_weight = 1 / comb(len(candidates), new_count)

        for spread in spreads(boosts, len(all_lines)):
            totals = np.zeros(len(STATS))

            for line, extra in zip(all_lines, spread, strict=True):
                if line.stat is None:
                    continue

                rolls_added = extra + (1 if (line.stat, line.absolute) in added else 0)
                one = one_roll(line.stat, line.absolute, roll)
                totals[STATS.index(line.stat)] += line.units + rolls_added * one

            chances.append(added_weight * multinomial(spread))
            totals_by_outcome.append(totals)

    return Outcomes(np.array(chances), np.array(totals_by_outcome))


type CountChances = tuple[tuple[tuple[int, ...], float], ...]  # (roll counts, chance)


def count_chances(counts: tuple[int, ...], upgrades: int) -> CountChances:
    """The lines' roll counts (sorted) after `upgrades` more, with their chances: new lines
    first (one roll each) up to four, then the rest spread over the lines alike."""
    new_lines = min(upgrades, max(MAX_SUBSTATS - len(counts), 0))
    lines = (*counts, *([1] * new_lines))
    chances: dict[tuple[int, ...], float] = {}

    for spread in spreads(upgrades - new_lines, len(lines)):
        key = tuple(sorted(count + extra for count, extra in zip(lines, spread, strict=True)))
        chances[key] = chances.get(key, 0) + multinomial(spread)

    return tuple(sorted(chances.items()))


@dataclass(frozen=True)
class ReworkBase:
    """What a rework keeps of a piece, and so all its outcomes depend on (hashable: reworks
    are cached)."""

    slot: Slot
    rank: int
    set_id: int
    faction: str | None


@dataclass(frozen=True)
class Scored:
    """Ways a piece can turn out: each one's chance, and its score for each type (a row per
    outcome, a column per type)."""

    chances: np.ndarray
    scores: np.ndarray


@lru_cache(maxsize=4096)
def reworked(base: ReworkBase, chances: CountChances, upgrades: int, scorer: Scorer) -> Scores:
    """A rework's scores, over the roll counts the piece may have when it's reworked (a
    piece below +12 is rolled to +12 first)."""
    outcomes = [rework_outcomes(base, counts, upgrades, scorer) for counts, _ in chances]
    weights = np.concatenate(
        [o.chances * chance for o, (_, chance) in zip(outcomes, chances, strict=True)]
    )
    return quantiles(weights, np.concatenate([o.scores for o in outcomes]), scorer)


@lru_cache(maxsize=4096)
def rework_outcomes(
    base: ReworkBase, counts: tuple[int, ...], upgrades: int, scorer: Scorer
) -> Scored:
    """Reworking lines holding `counts` rolls: a main stat alike among the slot's, then the
    lines' stats alike among what that main leaves (as permutations, since lines hold
    different roll counts). Upgrades still to come add their expected rolls."""
    slot, rank = base.slot, base.rank
    roll = roll_size(rank)
    per_main: list[Scored] = []

    for main in MAIN_STATS[slot]:
        candidates = [c for c in SUBSTATS[slot] if c != main_line(main)]
        rolls_of = np.array([one_roll(s, a, roll) for s, a in candidates])
        stat_index = np.array([STATS.index(s) for s, _ in candidates])
        picks = np.array(list(permutations(range(len(candidates)), len(counts))))
        rolls = np.array(counts) + upgrades / max(len(counts), 1)

        totals = np.zeros((len(picks), len(STATS)))

        for column, count in enumerate(rolls):
            np.add.at(
                totals,
                (np.arange(len(picks)), stat_index[picks[:, column]]),
                rolls_of[picks[:, column]] * count,
            )

        probability = 1 / len(MAIN_STATS[slot]) / len(picks)
        main_rolls = main_units(scorer.gear, slot, main, rank)
        allowed = types_for(base.set_id, slot, main, base.faction, scorer.types)
        per_main.append(
            Scored(
                np.full(len(picks), probability),
                score_matrix(totals, main, main_rolls, allowed, scorer),
            )
        )

    return Scored(
        np.concatenate([s.chances for s in per_main]),
        np.concatenate([s.scores for s in per_main]),
    )


def score_outcomes(
    outcomes: Outcomes,
    main: Stat,
    main_rolls: float,
    allowed: tuple[str, ...],
    scorer: Scorer,
) -> Scores:
    scores = score_matrix(outcomes.totals, main, main_rolls, allowed, scorer)
    return quantiles(outcomes.chances, scores, scorer)


def score_matrix(
    totals: np.ndarray, main: Stat, main_rolls: float, allowed: tuple[str, ...], scorer: Scorer
) -> np.ndarray:
    """(outcome, type) scores; types not allowed score nothing."""
    totals = totals.copy()
    totals[:, STATS.index(main)] += main_rolls
    scores = totals @ scorer.matrix.T
    scores += np.minimum(totals[:, HP_INDEX], totals[:, DEF_INDEX])[:, None] * scorer.balance
    mask = np.array([t.key in allowed for t in scorer.types])
    return np.where(mask, scores, 0.0)


def quantiles(weights: np.ndarray, scores: np.ndarray, scorer: Scorer) -> Scores:
    """Each column's quantile, then the best overall and of each kind."""
    by_type = [weighted_quantile(scores[:, column], weights) for column in range(scores.shape[1])]
    keys = [t.key for t in scorer.types]

    def best_of(kind: Kind) -> float:
        return max(
            (q for q, t in zip(by_type, scorer.types, strict=True) if t.kind is kind), default=0
        )

    best = max(by_type, default=0)
    fit = keys[by_type.index(best)] if best > 0 else None
    return Scores(best, best_of(Kind.DAMAGE), best_of(Kind.SUPPORT), fit)


def weighted_quantile(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    index = np.searchsorted(cumulative, QUANTILE * cumulative[-1])
    return float(values[order][min(index, len(values) - 1)])


def spreads(total: int, parts: int) -> list[tuple[int, ...]]:
    """Every way `total` rolls can fall on `parts` lines."""
    if parts == 0:
        return [()] if total == 0 else []

    if parts == 1:
        return [(total,)]

    return [
        (first, *rest) for first in range(total + 1) for rest in spreads(total - first, parts - 1)
    ]


def multinomial(spread: tuple[int, ...]) -> float:
    """The chance of this spread when each roll picks a line alike."""
    if not spread:
        return 1.0

    ways = factorial(sum(spread))

    for count in spread:
        ways //= factorial(count)

    return ways / len(spread) ** sum(spread)


def roll_size(rank: int) -> float:
    """A roll's size against a 6★ one."""
    return RANK_ROLL.get(rank, rank / 6)


def one_roll(stat: Stat, absolute: bool, size: float) -> float:
    """An average roll of a rank whose rolls are `size` of 6★ ones, in average 6★ rolls."""
    return roll_units(stat, absolute, ROLL_6.get((stat, absolute), 0)) * size


def main_line(main: Stat) -> tuple[Stat, bool]:
    """A main stat as a line: flat, but for C.DMG (always a %)."""
    return main, main is not Stat.CD


def roll_units(stat: Stat, absolute: bool, value: float) -> float:
    """`value` in average 6★ rolls of the stat; flat HP/ATK/DEF as a share of base, so it
    counts with the % line."""
    if absolute and stat in REFERENCE_BASE:
        return value / REFERENCE_BASE[stat] / ROLL_6[(stat, False)]

    return value / ROLL_6.get((stat, absolute), 1)


def line_units(stat: Stat | None, absolute: bool, value: float) -> float:
    return roll_units(stat, absolute, value) if stat is not None else 0.0


def main_units(gear: GearTables, slot: Slot, main: Stat, rank: int) -> float:
    """The main stat at +16 in rolls: `MAIN_ROLLS` at 6★, less at lower ranks."""
    values = gear.primary.get(GearLine(slot, *main_line(main)), {})

    if 6 not in values or rank not in values:
        return MAIN_ROLLS * rank / 6

    return MAIN_ROLLS * values[rank][-1] / values[6][-1]


def upgrades_left(level: int, to_level: int) -> int:
    return sum(1 for upgrade in UPGRADE_LEVELS if level < upgrade <= to_level)
