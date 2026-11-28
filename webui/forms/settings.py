"""
settings.py - the forms that change what's stored. The champion list's lock picker posts
`level`; the assumptions page posts `kind` (a `kind_key`) and `grade` (a `grade_key`, empty for
none) for a glyph, `flag` (a `Flag`) with `on` (present when ticked) for the rest, and `rule`
(a reserve `rule_key`) with `on` (present: add it, else remove it). The accessories pages post
a champion type whole: `type` (its key), `label`, `kind` (a `Kind`), `faction` (the game's
name, empty for any), `weight:<stat>` per stat and `main:<slot>:<stat>` (present when ticked)
per main stat that suits it, by the game's names; a set's value (`set`, its id, and
`factor`) or whether it targets a type (`set`, `type`, the type's key, and `on`, present
when ticked); `off_target`, the share an off-target type counts for; a rule (`rule`, a
`Rules` field's name, and `value`, 1 or 0 for a switch) or a set's own (`set`, `rule`, a
`SetRules` field's name, and `value`); then `target_free` for the spaces to leave, `on`
(present when ticked) to protect a piece, and `artifact_id` (repeated) for the pieces to sell.

- `parse_lock`: the lock picker's level
- `GlyphPlan`, `parse_glyph`: a glyph kind and the grade to assume for it
- `FlagSetting`, `parse_flag`: an assumption, on or off
- `ReserveSetting`, `parse_reserve_rule`: a reserve rule, added or removed
- `MAX_WEIGHT`, `TypeEdit`, `parse_champion_type`: a champion type as edited
- `MAX_SET_FACTOR`, `SetValue`, `parse_set_value`: a set's value
- `SetTarget`, `parse_set_target`: whether a set targets a type
- `parse_off_target`: what off-target types count for
- `RuleValue`, `parse_rule_value`: an accessory rule
- `SetRuleValue`, `parse_set_rule`: a set's own rule
- `MAX_TARGET_FREE`, `parse_target_free`: the inventory spaces to leave free
- `parse_protect`: a piece protected from the clean-up, or not
- `parse_sell`: the pieces to select for selling
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.accessories.cleanup import ACCESSORY_SPACE
from optimiser.accessories.roles import ACCESSORY_MAINS, TYPE_STATS, Kind, Mains
from optimiser.accessories.rules import SET_RULE_BOUNDS, RuleBounds, rule_bounds
from optimiser.account import LOCK_LEVELS, Account
from optimiser.assume import Flag
from optimiser.glyphs import parse_grade, parse_kind
from optimiser.labels import MARKER_LABELS
from optimiser.reserve import Rule, Tagged, Team, parse_rule
from optimiser.tables import GlyphGrade, GlyphKind, Stat, Tables
from webui.forms.common import FormErrors, parse_number

MAX_WEIGHT = 10
MAX_SET_FACTOR = 3
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
class TypeEdit:
    """A champion type as its row posts it (what it was made from isn't edited)."""

    key: str
    label: str
    kind: Kind
    faction: str | None  # None: any
    weights: tuple[tuple[Stat, float], ...]
    mains: Mains


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


def parse_champion_type(form: Mapping[str, str], factions: set[str]) -> TypeEdit | FormErrors:
    """`factions`: those a type may be for (the game's names)."""
    errors: list[str] = []
    key, label = form.get("type", ""), form.get("label", "").strip()
    kind, faction = form.get("kind", ""), form.get("faction", "") or None

    if not key.isdigit():
        errors.append("no such champion type")

    if not label:
        errors.append("a type needs a name")

    if kind not in Kind:
        errors.append(f"no such kind: {kind}")

    if faction is not None and faction not in factions:
        errors.append(f"no such faction: {faction}")

    weights = []

    for stat in TYPE_STATS:
        weight = parse_number(form, f"weight:{stat.value}", stat.name, errors)

        if not 0 <= weight <= MAX_WEIGHT:
            errors.append(f"weights are 0 to {MAX_WEIGHT}")
        elif weight:
            weights.append((stat, weight))

    mains = tuple(
        (slot, tuple(stat for stat in stats if f"main:{slot.value}:{stat.value}" in form))
        for slot, stats in ACCESSORY_MAINS
    )

    if errors:
        return FormErrors(list(dict.fromkeys(errors)))

    return TypeEdit(key, label, Kind(kind), faction, tuple(weights), mains)


@dataclass(frozen=True)
class SetValue:
    set_id: int
    factor: float


@dataclass(frozen=True)
class SetTarget:
    set_id: int
    type_key: str
    on: bool  # targets it; else doesn't


def parse_set_value(form: Mapping[str, str]) -> SetValue | FormErrors:
    errors: list[str] = []
    text = form.get("set", "")

    if not text.isdigit():
        errors.append("no such set")

    factor = parse_number(form, "factor", "value", errors, default=1)

    if not 0 <= factor <= MAX_SET_FACTOR:
        errors.append(f"a set's value is 0 to {MAX_SET_FACTOR}")

    if errors:
        return FormErrors(errors)

    return SetValue(int(text), factor)


def parse_set_target(form: Mapping[str, str], type_keys: set[str]) -> SetTarget | FormErrors:
    """`type_keys`: every type's."""
    text, key = form.get("set", ""), form.get("type", "")

    if not text.isdigit():
        return FormErrors(["no such set"])

    if key not in type_keys:
        return FormErrors(["that type is gone; reload the page"])

    return SetTarget(int(text), key, "on" in form)


def parse_off_target(form: Mapping[str, str]) -> float | FormErrors:
    errors: list[str] = []
    share = parse_number(form, "off_target", "off-target share", errors, default=-1)

    if errors or not 0 <= share <= 1:
        return FormErrors(errors or ["the off-target share is 0 to 1"])

    return share


@dataclass(frozen=True)
class RuleValue:
    name: str  # a `Rules` field's
    value: float


@dataclass(frozen=True)
class SetRuleValue:
    set_id: int
    name: str  # a `SetRules` field's
    value: int


def parse_rule_value(form: Mapping[str, str]) -> RuleValue | FormErrors:
    """A switch is 1 or 0; a whole number's rule takes whole numbers."""
    name = form.get("rule", "")

    if name not in (bounds := rule_bounds()):
        return FormErrors(["no such rule"])

    errors: list[str] = []
    value = parse_number(form, "value", "the rule", errors, default=-1)
    within = bounds[name] or RuleBounds(0, 1)

    if errors or not within.low <= value <= within.high:
        return FormErrors(errors or [f"the rule is {within.low:g} to {within.high:g}"])

    if within.whole or bounds[name] is None:
        return RuleValue(name, round(value))

    return RuleValue(name, value)


def parse_set_rule(form: Mapping[str, str]) -> SetRuleValue | FormErrors:
    text, name = form.get("set", ""), form.get("rule", "")

    if not text.isdigit():
        return FormErrors(["no such set"])

    if (bounds := SET_RULE_BOUNDS.get(name)) is None:
        return FormErrors(["no such rule"])

    value = form.get("value", "").strip()

    if not (value.isdigit() and bounds.low <= int(value) <= bounds.high):
        return FormErrors([f"a whole number, {bounds.low:g} to {bounds.high:g}"])

    return SetRuleValue(int(text), name, int(value))


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
