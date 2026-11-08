"""
assess.py - every accessory the account has (worn, in the inventory, or waiting in the
mailbox), each with its potential (`potential`) and its value: the potential,
raised where its set, faction and slot are short of good pieces and lowered where there are
plenty, and weighed by its set's meta tier (`roles.set_factor`; set-less pieces lowered).
The clean-up and the roll and rework lists share it.

- `Where`, `Assessed`, `Assessment`: the account's accessories, assessed
- `GOOD_SHARE`, `SCARCITY`, `PLENTY`: what good is, and what it's worth to be short
- `placed_accessories`, `potentials_of`: the account's accessories and their potentials (the
  slow part, worth keeping: only a piece's own state and the scorer change it)
- `assess_accessories`: the workflow
- `good_bars`, `scarcity_by_shelf`, `shelf_of`: its steps
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from optimiser.accessories.potential import ACCESSORIES, Piece, Potential, Scorer, assess
from optimiser.accessories.roles import set_factor
from optimiser.account import Account, Artifact, Locks, Slot

GOOD_SHARE = 0.25  # a piece is good when its potential is in its slot's top quarter
SCARCITY = {0: 1.15, 1: 1.05, 2: 1.0}  # by good pieces on the shelf; more than that: below
PLENTY = 0.9


class Where(StrEnum):
    WORN = "worn"
    INVENTORY = "inventory"
    MAILBOX = "mailbox"


type Shelf = tuple[int, str | None, Slot]  # set, faction, slot


@dataclass(frozen=True)
class Assessed:
    """`wearer`: the champion wearing it, if any; `wearer_locked`: they're locked, so it's not
    to be moved."""

    artifact: Artifact
    where: Where
    potential: Potential
    scarcity: float
    wearer_locked: bool
    wearer: int | None = None

    @property
    def value(self) -> float:
        """Its potential, weighed."""
        return self.weighed(self.potential.value())

    def weighed(self, score: float) -> float:
        """A score of the piece, weighed by its shortage and its set's meta tier."""
        return score * self.scarcity * set_factor(self.artifact.set_id)


@dataclass(frozen=True)
class Assessment:
    pieces: tuple[Assessed, ...]
    good_bars: dict[Slot, float]  # the potential a piece of the slot needs to be good

    def is_good(self, piece: Assessed) -> bool:
        """Its potential, weighed by its set's tier (not by shortage), against its slot's
        bar."""
        weighed = piece.potential.value() * set_factor(piece.artifact.set_id)
        return weighed >= self.good_bars[piece.artifact.slot]


def placed_accessories(account: Account) -> list[tuple[Artifact, Where]]:
    placed = [
        *(
            (a, Where.WORN if a.id in account.owners else Where.INVENTORY)
            for a in account.artifacts
        ),
        *((a, Where.MAILBOX) for a in account.mailbox),
    ]
    return [(a, where) for a, where in placed if a.slot in ACCESSORIES and a.primary.stat]


def potentials_of(
    account: Account, scorer: Scorer, known: Mapping[Piece, Potential]
) -> dict[Piece, Potential]:
    """Each accessory's potential, by what it depends on: `known` ones (by the same scorer)
    are kept, the rest scored."""
    potentials: dict[Piece, Potential] = {}

    for artifact, _ in placed_accessories(account):
        piece = Piece.of(artifact)

        if piece not in potentials:
            potentials[piece] = known[piece] if piece in known else assess(piece, scorer)

    return potentials


def assess_accessories(
    account: Account, by_piece: Mapping[Piece, Potential], locks: Locks
) -> Assessment:
    """`by_piece`: `potentials_of` the account."""
    placed = placed_accessories(account)
    potentials = {a.id: by_piece[Piece.of(a)] for a, _ in placed}
    owned = [(a, potentials[a.id]) for a, where in placed if where is not Where.MAILBOX]
    bars = good_bars(owned)
    scarcity = scarcity_by_shelf(owned, bars)

    def assessed(artifact: Artifact, where: Where) -> Assessed:
        wearer = account.owners.get(artifact.id)
        return Assessed(
            artifact,
            where,
            potentials[artifact.id],
            scarcity.get(shelf_of(artifact), SCARCITY[0]),
            wearer_locked=wearer is not None and locks.get(wearer, 0) > 0,
            wearer=wearer,
        )

    return Assessment(tuple(assessed(a, where) for a, where in placed), bars)


def good_bars(owned: list[tuple[Artifact, Potential]]) -> dict[Slot, float]:
    bars = {}

    for slot in ACCESSORIES:
        values = [p.value() for a, p in owned if a.slot is slot]
        bars[slot] = float(np.quantile(values, 1 - GOOD_SHARE)) if values else 0.0

    return bars


def scarcity_by_shelf(
    owned: list[tuple[Artifact, Potential]], bars: dict[Slot, float]
) -> dict[Shelf, float]:
    """Good pieces count whoever wears them: moving gear is free."""
    good = Counter(shelf_of(a) for a, p in owned if p.value() >= bars[a.slot])
    shelves = {shelf_of(a) for a, _ in owned}
    return {shelf: SCARCITY.get(good[shelf], PLENTY) for shelf in shelves}


def shelf_of(artifact: Artifact) -> Shelf:
    return artifact.set_id, artifact.faction, artifact.slot
