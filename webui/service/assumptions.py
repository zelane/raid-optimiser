"""
assumptions.py - the assumptions page: what solves assume (top levels, full ascension,
glyphs) and what gear is reserved (`optimiser.reserve`), kept in the store.

- `FlagView`, `GlyphChoice`, `GlyphRow`, `RuleView`, `RuleChoice`, `ReserveSection`,
  `AssumptionsPage`: the views
- `assumptions_page`, `set_assumption`, `plan_glyph_for`, `change_reserve_rule`: what the page
  asks for
- `flag_view`, `glyph_row`, `reserve_section`: what they share
"""

from collections import Counter
from dataclasses import dataclass

from optimiser.account import Account, GlyphGrade, GlyphKind, Preset
from optimiser.assume import FLAG_LABELS, Flag
from optimiser.glyphs import grade_key, kind_key
from optimiser.labels import (
    MARKER_LABELS,
    glyph_grade_label,
    glyph_kind_label,
    line_amount,
    rule_label,
)
from optimiser.paths import STORE
from optimiser.reserve import (
    GlobalPresets,
    Rule,
    Tagged,
    Team,
    reservations,
    reserved_count,
    rule_key,
)
from optimiser.settings import plan_glyph, read_assumptions, set_flag, set_reserve_rule
from webui.service.current import current_reserve_rules


@dataclass(frozen=True)
class FlagView:
    name: str
    label: str
    on: bool


@dataclass(frozen=True)
class GlyphChoice:
    key: str  # `grade_key`; "" for none
    label: str  # "6★ Legendary (+12)"


@dataclass(frozen=True)
class GlyphRow:
    """A glyph kind and the grade assumed for it ("" for none)."""

    key: str  # `kind_key`
    label: str
    choices: list[GlyphChoice]
    chosen: str


@dataclass(frozen=True)
class RuleView:
    key: str  # `rule_key`
    label: str
    pieces: int  # how many it reserves now


@dataclass(frozen=True)
class RuleChoice:
    """A rule that could be added: a tag ("Arena Build II · 4 champions") or a saved team
    ("cb · GeneralPve: Valerie, …")."""

    key: str  # `rule_key`
    label: str


@dataclass(frozen=True)
class ReserveSection:
    rules: list[RuleView]  # in the order added
    pieces: int  # all of them together (a piece can have several reasons)
    tags: list[RuleChoice]  # tags no rule has yet, with champions tagged
    teams: list[RuleChoice]  # saved teams no rule has yet
    global_key: str | None  # the global presets rule's key, if it isn't a rule yet


@dataclass(frozen=True)
class AssumptionsPage:
    flags: list[FlagView]
    glyphs: list[GlyphRow]
    reserve: ReserveSection


def assumptions_page(account: Account) -> AssumptionsPage:
    assumptions = read_assumptions(STORE, account)
    planned = assumptions.glyphs
    return AssumptionsPage(
        flags=[flag_view(flag, flag in assumptions.flags) for flag in Flag],
        glyphs=[glyph_row(account, kind, planned.get(kind)) for kind in account.tables.glyphs],
        reserve=reserve_section(account),
    )


def set_assumption(flag: Flag, on: bool) -> FlagView:
    set_flag(STORE, flag, on)
    return flag_view(flag, on)


def plan_glyph_for(account: Account, kind: GlyphKind, grade: GlyphGrade | None) -> GlyphRow:
    """None stops assuming the kind."""
    plan_glyph(STORE, kind, grade)
    return glyph_row(account, kind, grade)


def change_reserve_rule(account: Account, rule: Rule, on: bool) -> ReserveSection:
    set_reserve_rule(STORE, rule, on)
    return reserve_section(account)


def flag_view(flag: Flag, on: bool) -> FlagView:
    return FlagView(flag.value, FLAG_LABELS[flag], on)


def glyph_row(account: Account, kind: GlyphKind, chosen: GlyphGrade | None) -> GlyphRow:
    tops = account.tables.glyphs[kind]
    choices = [
        GlyphChoice(
            grade_key(grade), f"{glyph_grade_label(grade)} (+{line_amount(top, kind.absolute)})"
        )
        for grade, top in reversed(tops.items())
    ]
    return GlyphRow(
        key=kind_key(kind),
        label=glyph_kind_label(kind),
        choices=[GlyphChoice("", "None"), *choices],
        chosen=grade_key(chosen) if chosen else "",
    )


def reserve_section(account: Account) -> ReserveSection:
    rules = current_reserve_rules()
    reserved = reservations(account, rules)
    tagged = Counter(champion.marker for champion in account.champions.values())

    def team_choice(preset: Preset) -> RuleChoice:
        names = ", ".join(
            account.champions[i].name for i in preset.champion_ids if i in account.champions
        )
        return RuleChoice(rule_key(Team(preset.id)), f"{preset.name} · {preset.area}: {names}")

    tags = [Tagged(marker) for marker in MARKER_LABELS if tagged[marker]]
    teams = sorted((p for p in account.presets if p.champion_ids), key=lambda p: p.id)
    return ReserveSection(
        rules=[
            RuleView(rule_key(r), rule_label(r, account), reserved_count(reserved, r))
            for r in rules
        ],
        pieces=len(reserved),
        tags=[
            RuleChoice(rule_key(tag), f"{rule_label(tag, account)} · {tagged[tag.marker]}")
            for tag in tags
            if tag not in rules
        ],
        teams=[team_choice(preset) for preset in teams if Team(preset.id) not in rules],
        global_key=None if GlobalPresets() in rules else rule_key(GlobalPresets()),
    )
