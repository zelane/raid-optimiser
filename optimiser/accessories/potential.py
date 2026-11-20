"""
potential.py - what an accessory could become: every way its remaining upgrades can land
and, if it hasn't been reworked, every way a rework can re-pick it, each scored against the
champion types it could be for (`roles`), each type's counting for the share its set's
fit gives it (`roles.type_fits`: off-target types count less). A piece's potential is a
quantile of those scores, so concentrated rolls (a triple roll anywhere) count for their upside.

Scores are in average 6★ rolls: each stat's value (flat and % together, flat as a share of a
typical base stat), times the type's weight for it, plus the main stat as `MAIN_ROLLS` rolls
scaled by its rank's top value. Future rolls are average rolls. Each substat also counts the
best glyph a piece of its rank can take for it, whatever glyph it has now: any piece with the
stat can be glyphed, one without it can't, so having a stat is worth more than its rolls.

Upgrades (at +4, +8, +12, +16) add a substat until there are four, any the slot can roll
that the piece lacks alike, then a roll to one of the four alike. A rework keeps each line's
number of rolls, the set and the faction, and re-picks the main stat and which stat each line
is, alike among what the slot can roll.

- `ROLL_6`, `RANK_ROLL`, `REFERENCE_BASE`, `MAIN_ROLLS`, `UPGRADE_LEVELS`, `ROLL_TO`,
  `MAX_SUBSTATS`, `QUANTILE`, `ACCESSORIES`, `MAIN_STATS`, `Substat`, `SUBSTATS`: the game,
  and units
- `Scorer`, `make_scorer`: the types, the set fits and the glyphs' best rolls, as scoring
  needs them
- `Scores`, `Potential`: a piece's scores
- `PieceLine`, `Piece`: what a piece's potential depends on (a key to keep it by)
- `assess` (`piece_fits`): a piece's potential
- `Line`, `Outcomes`, `ReworkBase`, `Scored`: what the outcomes are worked out from, and are
- `natural`, `reworked` (`count_chances`, `rework_outcomes`): its outcomes, and their scores
  (`score_outcomes`, `raw_scores`, `quantiles`, `weighted_quantiles`)
- `spread_table`, `spreads`, `multinomial`, `roll_size`, `one_roll`, `main_line`,
  `roll_units`, `line_units`, `main_units`, `glyph_units`, `upgrades_left`: what they share
"""

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations, permutations
from math import comb, factorial
from typing import NamedTuple

import numpy as np

from optimiser.accessories.roles import ChampionType, Group, Kind, SetTable, type_fits
from optimiser.account import Artifact, GearLine, GearTables, GlyphGrade, GlyphKind, Slot, Stat

ACCESSORIES = (Slot.RING, Slot.AMULET, Slot.BANNER)
MAIN_STATS = {
    Slot.RING: (Stat.ATK, Stat.HP, Stat.DEF),
    Slot.AMULET: (Stat.ATK, Stat.CD, Stat.HP, Stat.DEF),
    Slot.BANNER: (Stat.ATK, Stat.HP, Stat.DEF, Stat.ACC, Stat.RES),
}


class Substat(NamedTuple):
    """One line a slot can roll: a stat, flat or %."""

    stat: Stat
    absolute: bool


BODY_LINES = tuple(
    Substat(s, absolute) for s in (Stat.ATK, Stat.HP, Stat.DEF) for absolute in (True, False)
)
SUBSTATS = {  # each line a slot can roll
    Slot.RING: BODY_LINES,
    Slot.AMULET: (
        Substat(Stat.ATK, True),
        Substat(Stat.HP, True),
        Substat(Stat.DEF, True),
        Substat(Stat.ACC, True),
        Substat(Stat.RES, True),
        Substat(Stat.CD, False),
    ),
    Slot.BANNER: (Substat(Stat.SPD, True), *BODY_LINES),
}

# An average 6★ roll of each line (measured on the account's gear): the unit scores count in.
ROLL_6 = {
    Substat(Stat.HP, False): 0.06,
    Substat(Stat.ATK, False): 0.06,
    Substat(Stat.DEF, False): 0.06,
    Substat(Stat.CR, False): 0.06,
    Substat(Stat.CD, False): 0.06,
    Substat(Stat.SPD, True): 5.5,
    Substat(Stat.ACC, True): 10.5,
    Substat(Stat.RES, True): 10.5,
    Substat(Stat.HP, True): 380,
    Substat(Stat.ATK, True): 22.5,
    Substat(Stat.DEF, True): 22.8,
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
    """The champion types as a (type, stat) weight matrix, the set fits, the tables that size
    main stats, and `glyphs`: each glyph kind's best roll a piece of each rank can take (none
    for C.DMG); `make_scorer` builds one."""

    types: tuple[ChampionType, ...]
    sets: SetTable
    gear: GearTables
    glyphs: dict[GlyphKind, dict[int, float]]
    matrix: np.ndarray
    balance: np.ndarray


def make_scorer(
    types: tuple[ChampionType, ...],
    sets: SetTable,
    gear: GearTables,
    glyphs: dict[GlyphKind, dict[GlyphGrade, float]],
) -> Scorer:
    matrix = np.array([[t.weight(stat) for stat in STATS] for t in types])
    caps = {  # as `glyphs.rank_caps`: a piece takes glyphs of its rank or lower
        kind: {
            rank: max((top for grade, top in grades.items() if grade.rank <= rank), default=0)
            for rank in range(1, 7)
        }
        for kind, grades in glyphs.items()
    }
    return Scorer(types, sets, gear, caps, matrix, np.array([t.balance for t in types]))


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


@dataclass(frozen=True)
class PieceLine:
    """A substat as scoring reads it: `value` without its glyph (a glyph can go on any piece
    with the stat, so it tells pieces apart by nothing), and the rolls it's had."""

    stat: Stat | None
    absolute: bool
    value: float
    rolls: int


@dataclass(frozen=True)
class Piece:
    """All a piece's potential depends on (with the scorer), so a key to keep it by: a piece
    scored once needs no rescoring until it's levelled or reworked."""

    slot: Slot
    set_id: int
    rank: int
    level: int
    main: Stat
    faction: str | None
    reworked: bool
    substats: tuple[PieceLine, ...]

    @staticmethod
    def of(artifact: Artifact) -> "Piece":
        return Piece(
            artifact.slot,
            artifact.set_id,
            artifact.rank,
            artifact.level,
            artifact.primary.stat or Stat.HP,
            artifact.faction,
            artifact.reworked,
            tuple(
                PieceLine(line.stat, line.absolute, line.value, line.rolls)
                for line in artifact.substats
            ),
        )


def piece_fits(scorer: Scorer, piece: Piece, main: Stat) -> tuple[float, ...]:
    """What each of the scorer's types counts for on the piece with `main`."""
    return type_fits(
        scorer.sets, scorer.types, Group(piece.slot, main, piece.set_id, piece.faction)
    )


def assess(piece: Piece, scorer: Scorer) -> Potential:
    lines = tuple(Line(line.stat, line.absolute, line_units(line)) for line in piece.substats)
    main = piece.main
    fits = piece_fits(scorer, piece, main)
    roll = roll_size(piece.rank)
    main_rolls = main_units(scorer.gear, piece.slot, main, piece.rank)

    glyphs = {sub: glyph_units(scorer, sub, piece.rank) for sub in SUBSTATS[piece.slot]}

    def natural_to(level: int) -> Scores:
        upgrades = upgrades_left(piece.level, level)
        outcomes = natural(piece.slot, main, lines, upgrades, roll, glyphs)
        return score_outcomes(outcomes, main, main_rolls, fits, scorer)

    rework = None

    if not piece.reworked:
        counts = tuple(line.rolls + 1 for line in piece.substats)
        rolled_to = max(piece.level, ROLL_TO)
        chances = count_chances(counts, upgrades_left(piece.level, rolled_to))
        upgrades = upgrades_left(rolled_to, UPGRADE_LEVELS[-1])
        fits_by_main = tuple(piece_fits(scorer, piece, m) for m in MAIN_STATS[piece.slot])
        base = ReworkBase(piece.slot, piece.rank, fits_by_main)
        rework = reworked(base, chances, upgrades, scorer)

    return Potential(
        now=natural_to(piece.level),
        at_roll_to=natural_to(max(piece.level, ROLL_TO)),
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
    slot: Slot,
    main: Stat,
    lines: tuple[Line, ...],
    upgrades: int,
    roll: float,
    glyphs: dict[tuple[Stat, bool], float],
) -> Outcomes:
    """Each way the upgrades can land. New substats come first, any combination alike; the
    rest spread over the four lines multinomially. Every line counts its best glyph
    (`glyphs`, in average rolls, by line)."""
    held = {Substat(line.stat, line.absolute) for line in lines if line.stat is not None}
    candidates = [c for c in SUBSTATS[slot] if c not in held and c != main_line(main)]
    new_count = min(upgrades, MAX_SUBSTATS - len(lines), len(candidates))
    spread, spread_chances = spread_table(upgrades - new_count, len(lines) + new_count)
    rolls_added = spread + np.array([0] * len(lines) + [1] * new_count, dtype=int)
    added_weight = 1 / comb(len(candidates), new_count)
    chances: list[np.ndarray] = []
    totals_by_outcome: list[np.ndarray] = []

    for added in combinations(candidates, new_count):
        all_lines = [*lines, *(Line(sub.stat, sub.absolute, 0.0) for sub in added)]
        totals = np.zeros((len(spread), len(STATS)))

        for column, line in enumerate(all_lines):
            if line.stat is None:
                continue

            sub = Substat(line.stat, line.absolute)
            one = one_roll(sub, roll)
            glyph = glyphs.get(sub, 0.0)
            totals[:, STATS.index(line.stat)] += line.units + glyph + rolls_added[:, column] * one

        chances.append(added_weight * spread_chances)
        totals_by_outcome.append(totals)

    return Outcomes(np.concatenate(chances), np.concatenate(totals_by_outcome))


@lru_cache(maxsize=64)
def spread_table(total: int, parts: int) -> tuple[np.ndarray, np.ndarray]:
    """`spreads` as a (spread, line) matrix, and each one's chance (`multinomial`)."""
    every = spreads(total, parts)
    table = np.array(every, dtype=int).reshape(len(every), parts)
    return table, np.array([multinomial(spread) for spread in every])


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
    are cached). `fits`: what each type counts for (in the scorer's order) with each of the
    slot's main stats (in `MAIN_STATS` order), by the piece's set and faction; many sets and
    factions share them."""

    slot: Slot
    rank: int
    fits: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class Scored:
    """Ways a piece can turn out: each one's chance, its score for each type (a row per
    outcome, a column per type) and its main stat (an index into the slot's `MAIN_STATS`)."""

    chances: np.ndarray
    scores: np.ndarray
    mains: np.ndarray


@lru_cache(maxsize=4096)
def reworked(base: ReworkBase, chances: CountChances, upgrades: int, scorer: Scorer) -> Scores:
    """A rework's scores, over the roll counts the piece may have when it's reworked (a
    piece below +12 is rolled to +12 first), each type's by its fit with the main stat."""
    outcomes = [
        rework_outcomes(base.slot, base.rank, counts, upgrades, scorer) for counts, _ in chances
    ]
    weights = np.concatenate(
        [o.chances * chance for o, (_, chance) in zip(outcomes, chances, strict=True)]
    )
    fits = np.array(base.fits)
    mains = np.concatenate([o.mains for o in outcomes])
    scores = np.concatenate([o.scores for o in outcomes]) * fits[mains]
    return quantiles(weights, scores, scorer)


@lru_cache(maxsize=1024)
def rework_outcomes(
    slot: Slot, rank: int, counts: tuple[int, ...], upgrades: int, scorer: Scorer
) -> Scored:
    """Reworking lines holding `counts` rolls: a main stat alike among the slot's, then the
    lines' stats alike among what that main leaves (as permutations, since lines hold
    different roll counts). Upgrades still to come add their expected rolls. Scored for
    every type: the piece's set and faction weigh them later (`reworked`). Each line counts
    its best glyph, as `natural`'s do."""
    roll = roll_size(rank)
    per_main: list[Scored] = []

    for main_index, main in enumerate(MAIN_STATS[slot]):
        candidates = [c for c in SUBSTATS[slot] if c != main_line(main)]
        rolls_of = np.array([one_roll(sub, roll) for sub in candidates])
        glyph_of = np.array([glyph_units(scorer, sub, rank) for sub in candidates])
        stat_index = np.array([STATS.index(sub.stat) for sub in candidates])
        picks = np.array(list(permutations(range(len(candidates)), len(counts))))
        rolls = np.array(counts) + upgrades / max(len(counts), 1)

        totals = np.zeros((len(picks), len(STATS)))

        for column, count in enumerate(rolls):
            np.add.at(
                totals,
                (np.arange(len(picks)), stat_index[picks[:, column]]),
                rolls_of[picks[:, column]] * count + glyph_of[picks[:, column]],
            )

        probability = 1 / len(MAIN_STATS[slot]) / len(picks)
        main_rolls = main_units(scorer.gear, slot, main, rank)
        per_main.append(
            Scored(
                np.full(len(picks), probability),
                raw_scores(totals, main, main_rolls, scorer),
                np.full(len(picks), main_index),
            )
        )

    return Scored(
        np.concatenate([s.chances for s in per_main]),
        np.concatenate([s.scores for s in per_main]),
        np.concatenate([s.mains for s in per_main]),
    )


def score_outcomes(
    outcomes: Outcomes,
    main: Stat,
    main_rolls: float,
    fits: tuple[float, ...],
    scorer: Scorer,
) -> Scores:
    scores = raw_scores(outcomes.totals, main, main_rolls, scorer)
    return quantiles(outcomes.chances, scores * np.array(fits), scorer)


def raw_scores(totals: np.ndarray, main: Stat, main_rolls: float, scorer: Scorer) -> np.ndarray:
    """(outcome, type) scores, before the piece's fits weigh them."""
    totals = totals.copy()
    totals[:, STATS.index(main)] += main_rolls
    scores = totals @ scorer.matrix.T
    scores += np.minimum(totals[:, HP_INDEX], totals[:, DEF_INDEX])[:, None] * scorer.balance
    return scores


def quantiles(weights: np.ndarray, scores: np.ndarray, scorer: Scorer) -> Scores:
    """Each column's quantile, then the best overall and of each kind."""
    by_type = [float(q) for q in weighted_quantiles(scores, weights)]
    keys = [t.key for t in scorer.types]

    def best_of(kind: Kind) -> float:
        return max(
            (q for q, t in zip(by_type, scorer.types, strict=True) if t.kind is kind), default=0
        )

    best = max(by_type, default=0)
    fit = keys[by_type.index(best)] if best > 0 else None
    return Scores(best, best_of(Kind.DAMAGE), best_of(Kind.SUPPORT), fit)


def weighted_quantiles(scores: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Each column's `QUANTILE`, the rows weighted by `weights`: all columns in one go."""
    order = np.argsort(scores, axis=0)
    cumulative = np.cumsum(weights[order], axis=0)
    index = np.minimum((cumulative < QUANTILE * cumulative[-1]).sum(axis=0), len(scores) - 1)
    columns = np.arange(scores.shape[1])
    return scores[order[index, columns], columns]


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


def one_roll(sub: Substat, size: float) -> float:
    """An average roll of a rank whose rolls are `size` of 6★ ones, in average 6★ rolls."""
    return roll_units(sub, ROLL_6.get(sub, 0)) * size


def main_line(main: Stat) -> Substat:
    """A main stat as a line: flat, but for C.DMG (always a %)."""
    return Substat(main, main is not Stat.CD)


def roll_units(sub: Substat, value: float) -> float:
    """`value` in average 6★ rolls of the stat; flat HP/ATK/DEF as a share of base, so it
    counts with the % line."""
    if sub.absolute and sub.stat in REFERENCE_BASE:
        return value / REFERENCE_BASE[sub.stat] / ROLL_6[Substat(sub.stat, False)]

    return value / ROLL_6.get(sub, 1)


def line_units(line: PieceLine) -> float:
    return roll_units(Substat(line.stat, line.absolute), line.value) if line.stat else 0.0


def glyph_units(scorer: Scorer, sub: Substat, rank: int) -> float:
    """The best glyph a piece of `rank` can take on a line, in average rolls (0: no glyph
    for it)."""
    top = scorer.glyphs.get(GlyphKind(sub.stat, sub.absolute), {}).get(rank, 0)
    return roll_units(sub, top)


def main_units(gear: GearTables, slot: Slot, main: Stat, rank: int) -> float:
    """The main stat at +16 in rolls: `MAIN_ROLLS` at 6★, less at lower ranks."""
    values = gear.primary.get(GearLine(slot, *main_line(main)), {})

    if 6 not in values or rank not in values:
        return MAIN_ROLLS * rank / 6

    return MAIN_ROLLS * values[rank][-1] / values[6][-1]


def upgrades_left(level: int, to_level: int) -> int:
    return sum(1 for upgrade in UPGRADE_LEVELS if level < upgrade <= to_level)
