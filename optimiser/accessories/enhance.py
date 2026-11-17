"""
enhance.py - which accessories to spend on first, for gear enhancement events. Rolling to +12
is cheap and shows most of a piece, so pieces below +12 rank by their potential there (or
reworked once there, whichever is better); +16 is dear, so only pieces already good once +16
is reached are listed for it; a rework is worth it where its potential beats the piece's own
by the rules' `rework_margin`. All rank by value (scarcity counted) and leave out what the
clean-up drops.

- `Step`, `Candidate`: what to do to a piece, and why it's listed
- `roll_list`, `finish_list`, `rework_list`: the lists
- `rolled_value`, `owned`: what they share
"""

from dataclasses import dataclass
from enum import StrEnum

from optimiser.accessories.assess import Assessed, Assessment, Where
from optimiser.accessories.potential import ROLL_TO, UPGRADE_LEVELS


class Step(StrEnum):
    ROLL = "roll to +12"
    FINISH = "roll to +16"
    REWORK = "rework"


@dataclass(frozen=True)
class Candidate:
    """`priority`: what the list ranks by. `before`, `after`: the piece's scores now and once
    the step is done (quantile scores)."""

    piece: Assessed
    step: Step
    priority: float
    before: float
    after: float


def roll_list(assessment: Assessment, dropped: set[int]) -> list[Candidate]:
    """By the better of the piece at +12 and reworked once there: a +0 Merciless amulet of
    any main stat may become a C.DMG one."""
    candidates = [
        Candidate(
            piece,
            Step.ROLL,
            piece.weighed(after := rolled_value(piece)),
            piece.potential.now.best,
            after,
        )
        for piece in owned(assessment, dropped)
        if piece.artifact.level < ROLL_TO
    ]
    return sorted(candidates, key=lambda c: c.priority, reverse=True)


def finish_list(assessment: Assessment, dropped: set[int]) -> list[Candidate]:
    """Only pieces good at +16 on their own rolls (a rework doesn't count here)."""
    candidates = [
        Candidate(
            piece,
            Step.FINISH,
            piece.weighed(piece.potential.natural.best),
            piece.potential.now.best,
            piece.potential.natural.best,
        )
        for piece in owned(assessment, dropped)
        if ROLL_TO <= piece.artifact.level < UPGRADE_LEVELS[-1]
        and piece.potential.natural.best >= assessment.good_bars[piece.artifact.slot]
    ]
    return sorted(candidates, key=lambda c: c.priority, reverse=True)


def rework_list(assessment: Assessment, dropped: set[int]) -> list[Candidate]:
    candidates = [
        Candidate(
            piece,
            Step.REWORK,
            piece.weighed(rework.best - piece.potential.natural.best),
            piece.potential.natural.best,
            rework.best,
        )
        for piece in owned(assessment, dropped)
        if (rework := piece.potential.rework) is not None
        and piece.artifact.level >= ROLL_TO
        and rework.best > piece.potential.natural.best * assessment.rules.rework_margin
    ]
    return sorted(candidates, key=lambda c: c.priority, reverse=True)


def rolled_value(piece: Assessed) -> float:
    rework = piece.potential.rework
    return max(piece.potential.at_roll_to.best, rework.best if rework else 0)


def owned(assessment: Assessment, dropped: set[int]) -> list[Assessed]:
    """In the inventory or worn: mailbox pieces have to be claimed first. Special variants
    are left alone."""
    return [
        piece
        for piece in assessment.pieces
        if piece.where is not Where.MAILBOX
        and piece.artifact.id not in dropped
        and not piece.artifact.special()
    ]
