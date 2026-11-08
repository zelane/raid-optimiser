"""
glyphs.py - glyphs assumed on gear: for each kind the account assumes, every substat of that
kind is taken as glyphed with a top roll of the chosen grade, unless its own glyph is better.
A piece takes glyphs up to its own rank, so below 6* the roll is capped at the best glyph
that rank allows. Only stats a solve wants more of are glyphed: a stat it doesn't use would
only pad the totals, and one it only caps would be held back by a glyph no one would apply.
The account's real gear is left alone; solves use the glyphed copy.

- `Planned`: the grade assumed for each kind
- `for_request`: the kinds a solve can use
- `with_glyphs`: an account with them applied to its gear
- `rank_caps`: the best roll a piece of each rank can take
- `kind_key`, `grade_key`, `parse_kind`, `parse_grade`: how kinds and grades are written
- `glyph_line`: one substat, glyphed
"""

from collections.abc import Mapping
from dataclasses import replace

from optimiser.account import Account, GlyphGrade, GlyphKind, Stat, StatLine
from optimiser.solve import Request, directions

type Planned = Mapping[GlyphKind, GlyphGrade]


def for_request(planned: Planned, request: Request) -> Planned:
    """Kinds whose stat the request wants more of: a minimum, a ranked stat, or one the
    ranked skill's damage uses (its formula's stats and C.DMG)."""
    wanted = directions(request)
    return {kind: grade for kind, grade in planned.items() if wanted.get(kind.stat, 0) > 0}


def with_glyphs(account: Account, planned: Planned) -> Account:
    """Main stats and ascension bonuses can't be glyphed: substats only."""
    if not planned:
        return account

    glyphs = account.tables.glyphs
    tops = {kind: glyphs[kind][grade] for kind, grade in planned.items()}
    caps = {kind: rank_caps(glyphs[kind]) for kind in planned}
    by_rank = {
        rank: {kind: min(top, caps[kind].get(rank, 0)) for kind, top in tops.items()}
        for rank in {artifact.rank for artifact in account.artifacts}
    }
    artifacts = tuple(
        replace(
            artifact,
            substats=tuple(glyph_line(line, by_rank[artifact.rank]) for line in artifact.substats),
        )
        for artifact in account.artifacts
    )
    return replace(account, artifacts=artifacts)


def rank_caps(grades: Mapping[GlyphGrade, float]) -> dict[int, float]:
    """Piece rank -> the top roll of the best glyph of the kind it can take (rank at most
    its own)."""
    return {
        rank: max((top for grade, top in grades.items() if grade.rank <= rank), default=0)
        for rank in range(1, 7)
    }


def glyph_line(line: StatLine, tops: Mapping[GlyphKind, float]) -> StatLine:
    if line.stat is None:
        return line

    top = tops.get(GlyphKind(line.stat, line.absolute), 0)
    return replace(line, planned_glyph=top) if top > line.glyph else line


def kind_key(kind: GlyphKind) -> str:
    """ "SPD", "HP%"."""
    return kind.stat.name + ("" if kind.absolute else "%")


def parse_kind(text: str) -> GlyphKind | None:
    name = text.removesuffix("%")

    if name not in Stat.__members__:
        return None

    return GlyphKind(Stat[name], not text.endswith("%"))


def grade_key(grade: GlyphGrade) -> str:
    """ "6-Legendary"."""
    return f"{grade.rank}-{grade.rarity}"


def parse_grade(text: str) -> GlyphGrade | None:
    rank, _, rarity = text.partition("-")
    return GlyphGrade(int(rank), rarity) if rank.isdigit() and rarity else None
