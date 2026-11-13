"""
assume.py - what a solve assumes beyond the gear as it is: the champion at their rank's top
level, gear levelled to the top (main stat only: substat rolls can't be foreseen), gear that's
been ascended taken to full ascension (gear never ascended has no bonus stat yet to raise),
and glyphs (`optimiser.glyphs`). All account-wide, kept in the store. The snapshot is left
alone: a solve gets an assumed copy of the account and its request.

- `Flag`, `FLAG_LABELS`, `Assumptions`: what can be assumed
- `assume`: an account and request with them applied
- `top_level`, `levelled`, `ascended`: the champion and one piece, assumed
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from optimiser.account import Account, Artifact, Champion, GearLine, GearTables
from optimiser.glyphs import Planned, for_request, with_glyphs
from optimiser.solve import Request

LEVELS_PER_GRADE = 10  # a champion's top level is 10 per star


class Flag(StrEnum):
    """As the store names them."""

    CHAMPION_LEVEL = "max_champion_level"
    GEAR_LEVEL = "max_gear_level"
    ASCENSION = "max_ascension"


FLAG_LABELS = {
    Flag.CHAMPION_LEVEL: "Champion at the top level of their rank",
    Flag.GEAR_LEVEL: "Gear at +16 (main stat only; substat rolls can't be foreseen)",
    Flag.ASCENSION: "Ascended gear fully ascended (gear never ascended has no bonus yet)",
}


@dataclass(frozen=True)
class Assumptions:
    flags: frozenset[Flag]
    glyphs: Planned


def assume(account: Account, request: Request, assumptions: Assumptions) -> tuple[Account, Request]:
    """Glyphs only go on stats the request wants more of (`glyphs.for_request`)."""
    flags, gear = assumptions.flags, account.tables.gear

    if Flag.CHAMPION_LEVEL in flags:
        request = replace(request, champion=top_level(request.champion))

    if Flag.GEAR_LEVEL in flags or Flag.ASCENSION in flags:
        artifacts = tuple(
            ascended(a, gear) if Flag.ASCENSION in flags else a
            for a in (
                levelled(a, gear) if Flag.GEAR_LEVEL in flags else a for a in account.artifacts
            )
        )
        account = replace(account, artifacts=artifacts)

    return with_glyphs(account, for_request(assumptions.glyphs, request)), request


def top_level(champion: Champion) -> Champion:
    """At the top level of their current rank; ranking up is another matter."""
    return replace(champion, level=max(champion.level, champion.grade * LEVELS_PER_GRADE))


def levelled(artifact: Artifact, gear: GearTables) -> Artifact:
    """The main stat at the top level; unchanged when the table doesn't know the stat."""
    primary = artifact.primary

    if artifact.level >= gear.max_level or primary.stat is None:
        return artifact

    values = gear.primary.get(GearLine(artifact.slot, primary.stat, primary.absolute), {})
    if artifact.rank not in values:
        return artifact

    return replace(
        artifact,
        primary=replace(primary, planned_value=values[artifact.rank][gear.max_level]),
        planned_level=gear.max_level,
    )


def ascended(artifact: Artifact, gear: GearTables) -> Artifact:
    """Fully ascended (one level per star), if it's been ascended at all."""
    line = artifact.ascension

    if line is None or line.stat is None or artifact.ascend_level >= artifact.rank:
        return artifact

    values = gear.ascension.get(GearLine(artifact.slot, line.stat, line.absolute), {})
    if artifact.rank not in values:
        return artifact

    return replace(
        artifact,
        ascension=replace(line, planned_value=values[artifact.rank][artifact.rank - 1]),
        planned_ascend_level=artifact.rank,
    )
