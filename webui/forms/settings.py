"""
settings.py - the forms that change what's stored. The champion list's lock picker posts
`level`; the assumptions page posts `kind` (a `kind_key`) and `grade` (a `grade_key`, empty for
none) for a glyph, `flag` (a `Flag`) with `on` (present when ticked) for the rest, and `rule`
(a reserve `rule_key`) with `on` (present: add it, else remove it). The accessories pages post
`key` ("<type>:<stat>", by the store's names) with `weight` for a champion type's weight,
`target_free` for the spaces to leave, `on` (present when ticked) to protect a piece, and
`artifact_id` (repeated) for the pieces to sell.

- `parse_lock`: the lock picker's level
- `GlyphPlan`, `parse_glyph`: a glyph kind and the grade to assume for it
- `FlagSetting`, `parse_flag`: an assumption, on or off
- `ReserveSetting`, `parse_reserve_rule`: a reserve rule, added or removed
- `MAX_WEIGHT`, `WeightSetting`, `parse_weight`: a champion type's weight for a stat
- `MAX_TARGET_FREE`, `parse_target_free`: the inventory spaces to leave free
- `parse_protect`: a piece protected from the clean-up, or not
- `parse_sell`: the pieces to select for selling
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.accessories.cleanup import ACCESSORY_SPACE
from optimiser.accessories.roles import TypeKey
from optimiser.account import LOCK_LEVELS, Account, GlyphGrade, GlyphKind, Stat, Tables
from optimiser.assume import Flag
from optimiser.glyphs import parse_grade, parse_kind
from optimiser.labels import MARKER_LABELS
from optimiser.reserve import Rule, Tagged, Team, parse_rule
from webui.forms.common import FormErrors, parse_number

MAX_WEIGHT = 10
MAX_TARGET_FREE = ACCESSORY_SPACE


@dataclass(frozen=True)
class GlyphPlan:
    """A glyph kind, and the grade to assume for it (None: none)."""

    kind: GlyphKind
    grade: GlyphGrade | None


@dataclass(frozen=True)
class FlagSetting:
    flag: Flag
    on: bool


@dataclass(frozen=True)
class WeightSetting:
    """A standard champion type's weight for a stat."""

    key: TypeKey
    stat: Stat
    weight: float


def parse_lock(form: Mapping[str, str]) -> int | FormErrors:
    """0 unlocks."""
    text = form.get("level", "").strip()

    if not (text.isdigit() and (int(text) == 0 or int(text) in LOCK_LEVELS)):
        return FormErrors([f"lock level must be 0 to {max(LOCK_LEVELS)}"])

    return int(text)


def parse_glyph(form: Mapping[str, str], tables: Tables) -> GlyphPlan | FormErrors:
    kind = parse_kind(form.get("kind", ""))

    if kind is None or kind not in tables.glyphs:
        return FormErrors(["no such glyph"])

    text = form.get("grade", "")
    if not text:
        return GlyphPlan(kind, None)

    grade = parse_grade(text)
    if grade is None or grade not in tables.glyphs[kind]:
        return FormErrors([f"no such glyph grade: {text}"])

    return GlyphPlan(kind, grade)


def parse_flag(form: Mapping[str, str]) -> FlagSetting | FormErrors:
    name = form.get("flag", "")

    if name not in Flag:
        return FormErrors([f"no such assumption: {name}"])

    return FlagSetting(Flag(name), "on" in form)


@dataclass(frozen=True)
class ReserveSetting:
    rule: Rule
    on: bool  # added; else removed


def parse_reserve_rule(form: Mapping[str, str], account: Account) -> ReserveSetting | FormErrors:
    """A rule to add must name a tag the game has or a saved team; any can be removed."""
    rule, on = parse_rule(form.get("rule", "")), "on" in form

    match rule:
        case None:
            return FormErrors(["no such reserve rule"])

        case Tagged(marker=marker) if on and marker not in MARKER_LABELS:
            return FormErrors([f"no champion tag {marker}"])

        case Team(preset_id=preset_id) if on and account.preset(preset_id) is None:
            return FormErrors(["that saved team is gone; sync and reload"])

        case _:
            return ReserveSetting(rule, on)


def parse_weight(form: Mapping[str, str]) -> WeightSetting | FormErrors:
    match form.get("key", "").split(":"):
        case [type_name, stat] if type_name in TypeKey and stat in Stat:
            key, weighed = TypeKey(type_name), Stat(stat)

        case _:
            return FormErrors(["no such weight"])

    errors: list[str] = []
    weight = parse_number(form, "weight", "weight", errors)

    if not errors and not 0 <= weight <= MAX_WEIGHT:
        errors.append(f"weights are 0 to {MAX_WEIGHT}")

    return FormErrors(errors) if errors else WeightSetting(key, weighed, weight)


def parse_target_free(form: Mapping[str, str]) -> int | FormErrors:
    text = form.get("target_free", "").strip()

    if not (text.isdigit() and int(text) <= MAX_TARGET_FREE):
        return FormErrors([f"free spaces must be a whole number, 0 to {MAX_TARGET_FREE}"])

    return int(text)


def parse_protect(form: Mapping[str, str]) -> bool:
    return "on" in form


def parse_sell(fields: list[str], to_sell: set[int]) -> list[int] | FormErrors:
    """Only pieces the plan sells now: an old page can't sell what it no longer would."""
    if not all(text.isdigit() for text in fields):
        return FormErrors(["artifact ids must be numbers"])

    artifact_ids = list(dict.fromkeys(int(text) for text in fields))

    if not artifact_ids:
        return FormErrors(["tick at least one piece"])

    if stale := [artifact_id for artifact_id in artifact_ids if artifact_id not in to_sell]:
        return FormErrors([f"{len(stale)} pieces are no longer to sell; reload the page"])

    return artifact_ids
