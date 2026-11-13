"""
forms.py - the request form's fields into a `Request`, or the reasons they can't be one.
The boundary: past here the solver sees only valid, typed requests.

Fields: `min_<STAT>`/`max_<STAT>` (C.RATE and C.DMG in %), `set_<n>` with `pieces_<n>` (any
number of rows, any `n`), `rank_<STAT>` (a priority, 1 first), `rank_DAMAGE` with
`damage_skill` (skill id) and `enemy_def`, `slack` (%), `builds`, `pool` (a `pool_name`),
`above_level`, `form` (which of a mythical's forms, 0 first; absent: the first). The equip
button posts `artifact_ids`, comma-separated; the champion list's lock picker posts `level`;
the assumptions page posts `kind` (a `kind_key`) and `grade` (a `grade_key`, empty for none)
for a glyph, and `flag` (a `Flag`) with `on` (present when ticked) for the rest. The
accessories pages post `key` ("<type>:<stat>", by the store's names) with `weight` for a
champion type's weight, `target_free` for the spaces to leave, `on` (present when ticked) to
protect a piece, and `artifact_id` (repeated) for the pieces to sell. The Chimera page's
`slot` (repeated, one per team slot) is a champion picked from its list, which ends in
"#<champion id>", or part of a champion's name typed in, or empty for an open slot; `want`
(repeated) a debuff, buff or effect every team must bring besides (a `Tag.key`, one of
`chimera.wantable`); `gear` (repeated) a set or relic any champion may wear (a `Gear.key`;
`gear_set` present: the list is as sent, else the defaults); `assume` (repeated) something
assumed: "<tag key>" for the team, "<champion id>@<tag key>" for one champion.

- `MAX_BUILDS`, `DEFAULT_ENEMY_DEF`, `DEFAULT_ABOVE_LEVEL`: the form's shape
- `FormErrors`: what's wrong with a submitted form
- `GlyphPlan`, `FlagSetting`, `WeightSetting`: what the assumption and weight forms set
- `parse_request`: the boundary
- `parse_equip`: the equip button's pieces
- `parse_lock`: the lock picker's level
- `parse_glyph`: a glyph kind and the grade to assume for it
- `parse_flag`: an assumption, on or off
- `MAX_WEIGHT`, `parse_weight`: a champion type's weight for a stat
- `MAX_TARGET_FREE`, `parse_target_free`: the inventory spaces to leave free
- `parse_protect`: a piece protected from the clean-up, or not
- `parse_sell`: the pieces to select for selling
- `DEFAULT_COLUMN`, `GRADES`, `FIRST_SHOWN`, `MAX_LISTED`: the Chimera page's shape
- `Offers`, `Fill`, `ChimeraRequest`, `Unknown`: what it can pick from, and what it asks
- `parse_chimera`: its boundary
- `Unmatched`, `SlotPick`, `parse_slots` (`parse_slot`): the Chimera team's slots
- `parse_wanted`, `parse_gear`, `parse_assumed`, `parse_fill`, `assume_entry`: its steps
- `parse_form`, `parse_limits`, `parse_sets`, `parse_ranking`, `parse_damage`,
  `parse_number`: its steps
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace

from optimiser.accessories.cleanup import ACCESSORY_SPACE
from optimiser.accessories.roles import TypeKey
from optimiser.account import (
    LOCK_LEVELS,
    Account,
    Champion,
    GlyphGrade,
    GlyphKind,
    Locks,
    Stat,
    Stats,
    Tables,
)
from optimiser.assume import Flag
from optimiser.chimera.gear import DEFAULT_GEAR, Assumed, Gear, Loadout, assumed_gear
from optimiser.chimera.tags import Tag
from optimiser.chimera.trials import PARTS, TEAM_SIZE
from optimiser.damage import DamageGoal, Unsupported, damage_goal
from optimiser.glyphs import parse_grade, parse_kind
from optimiser.labels import PERCENT_STATS, STAT_LABELS, parse_pool
from optimiser.solve import MAX_PIECES, Goal, Request

DEFAULT_ENEMY_DEF = 6000
DEFAULT_ABOVE_LEVEL = 8
MAX_BUILDS = 10
MAX_WEIGHT = 10
MAX_TARGET_FREE = ACCESSORY_SPACE


@dataclass(frozen=True)
class FormErrors:
    messages: list[str]


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


def parse_request(
    form: Mapping[str, str], champion: Champion, account: Account, locks: Locks
) -> Request | FormErrors:
    errors: list[str] = []
    champion = parse_form(form, champion, account, errors)
    minimums = parse_limits(form, "min", errors)
    maximums = parse_limits(form, "max", errors)
    set_minimums = parse_sets(form, account, errors)
    ranking = parse_ranking(form, champion, account, errors)
    slack = parse_number(form, "slack", "slack", errors, default=1.0)
    builds = parse_number(form, "builds", "builds", errors, default=3)
    above_level = parse_number(form, "above_level", "item level", errors, DEFAULT_ABOVE_LEVEL)
    pool = parse_pool(form.get("pool", "all"), locks)

    if not 0 <= slack <= 50:
        errors.append("slack must be between 0 and 50 %")

    if not 1 <= builds <= MAX_BUILDS:
        errors.append(f"builds must be between 1 and {MAX_BUILDS}")

    if pool is None:
        errors.append("unknown gear pool")

    if errors or pool is None:
        return FormErrors(errors)

    return Request(
        champion=champion,
        minimums=minimums,
        maximums=maximums,
        set_minimums=set_minimums,
        ranking=ranking,
        slack=slack / 100,
        builds=int(builds),
        pool=pool,
        above_level=int(above_level),
    )


def parse_equip(form: Mapping[str, str], account: Account) -> list[int] | FormErrors:
    fields = [text.strip() for text in form.get("artifact_ids", "").split(",") if text.strip()]

    if not all(text.isdigit() for text in fields):
        return FormErrors(["artifact ids must be numbers"])

    artifact_ids = [int(text) for text in fields]
    known = {artifact.id for artifact in account.artifacts}

    if not 1 <= len(artifact_ids) <= MAX_PIECES:
        return FormErrors([f"equip between 1 and {MAX_PIECES} pieces"])

    if unknown := [artifact_id for artifact_id in artifact_ids if artifact_id not in known]:
        return FormErrors([f"pieces no longer in the account: {unknown}; run the build again"])

    return artifact_ids


def parse_lock(form: Mapping[str, str]) -> int | FormErrors:
    """0 unlocks."""
    text = form.get("level", "").strip()

    if not (text.isdigit() and (int(text) == 0 or int(text) in LOCK_LEVELS)):
        return FormErrors([f"lock level must be 0 to {max(LOCK_LEVELS)}"])

    return int(text)


DEFAULT_COLUMN = "Tail"  # where the game's data puts Ultra Nightmare's mythical materials
GRADES = (6, 5, 4)
FIRST_SHOWN = 3  # teams a run lists at first
MAX_LISTED = 300  # most a page lists
TRUE = ("true", "1", "on", "yes")


@dataclass(frozen=True)
class Unmatched:
    """Text typed in a slot that isn't one champion: kept for the user to fix, and why."""

    text: str
    reason: str


type SlotPick = Champion | Unmatched | None


@dataclass(frozen=True)
class Offers:
    """What the Chimera page can pick from: tags to want or assume, and gear to allow."""

    tags: list[Tag]
    gear: list[Gear]


@dataclass(frozen=True)
class Fill:
    """Search for teams around the slots: list the first `listed`, the trials showing option
    number `option` (the first, if there's no such option)."""

    listed: int
    option: int


@dataclass(frozen=True)
class ChimeraRequest:
    """What the Chimera page asks for: the rotation's column (one of `PARTS`), the champions
    to search from (`min_grade`★ up), the slots as typed, what every team must bring, what it
    can wear or is assumed to have, and `fill`: a search (None: the slots as they are)."""

    column: str
    min_grade: int
    picks: tuple[SlotPick, ...]
    wanted: tuple[Tag, ...]
    loadout: Loadout
    fill: Fill | None


@dataclass(frozen=True)
class Unknown:
    """The page asked for doesn't exist (a column or rank there isn't)."""

    reason: str


def parse_chimera(
    query: Mapping[str, list[str]], account: Account, offers: Offers
) -> ChimeraRequest | Unknown | FormErrors:
    """The query's fields (each name's values, in order; a single value is the last)."""

    def last(name: str, default: str) -> str:
        return (query.get(name) or [default])[-1]

    column = last("column", DEFAULT_COLUMN)
    if column not in PARTS:
        return Unknown(f"no {column} column: {', '.join(PARTS)}")

    grade = last("min_grade", str(GRADES[0]))
    if not grade.isdigit() or int(grade) not in GRADES:
        return Unknown(f"rank {grade} isn't offered")

    picks = parse_slots(query.get("slot", []), account, TEAM_SIZE)
    wanted = parse_wanted(query.get("want", []), offers.tags)
    allowed = query.get("gear", []) if "gear_set" in query else list(DEFAULT_GEAR)
    gear = parse_gear(allowed, offers.gear)
    entries = query.get("assume", []) + assume_entry(query, account)
    assumed = parse_assumed(entries, account, offers.tags)
    if (
        isinstance(picks, FormErrors)
        or isinstance(wanted, FormErrors)
        or isinstance(gear, FormErrors)
        or isinstance(assumed, FormErrors)
    ):
        parsed = (picks, wanted, gear, assumed)
        return FormErrors([m for p in parsed if isinstance(p, FormErrors) for m in p.messages])

    team_assumed, single = assumed
    return ChimeraRequest(
        column=column,
        min_grade=int(grade),
        picks=picks,
        wanted=wanted,
        loadout=Loadout(gear + team_assumed, single),
        fill=parse_fill(query) if last("run", "").lower() in TRUE else None,
    )


def parse_fill(query: Mapping[str, list[str]]) -> Fill:
    """How many teams to list (`FIRST_SHOWN` to `MAX_LISTED`) and which to show; numbers that
    aren't fall back to the first."""

    def number(name: str, default: int) -> int:
        text = (query.get(name) or [""])[-1]
        return int(text) if text.isdigit() else default

    listed = min(max(number("listed", FIRST_SHOWN), FIRST_SHOWN), MAX_LISTED)
    return Fill(listed, number("option", 1))


def assume_entry(query: Mapping[str, list[str]], account: Account) -> list[str]:
    """The assume form's new entry, if any: what (a tag key) and who (a champion as picked or
    typed; none: the team), as `parse_assumed` reads it."""
    what = (query.get("assume_what") or [""])[-1]
    if not what:
        return []

    who = parse_slot((query.get("assume_who") or [""])[-1].strip(), account)
    return [f"{who.id}@{what}" if isinstance(who, Champion) else what]


CHAMPION_ID = re.compile(r"#(\d+)\s*$")
SHOWN_MATCHES = 3


def parse_slots(texts: list[str], account: Account, size: int) -> tuple[SlotPick, ...] | FormErrors:
    """`size` slots, None where open; extra fields are an error, missing ones are open."""
    if len(texts) > size:
        return FormErrors([f"a team has {size} slots"])

    padded = texts + [""] * (size - len(texts))
    return tuple(parse_slot(text.strip(), account) for text in padded)


def parse_slot(text: str, account: Account) -> SlotPick:
    """A pick from the list ("… #<id>"), or a name typed in part: the best copy of the one
    champion whose name has it (an exact name wins)."""
    if not text:
        return None

    if match := CHAMPION_ID.search(text):
        champion = account.champions.get(int(match.group(1)))
        return champion or Unmatched(text, "no such champion")

    wanted = text.casefold()
    names = {c.name for c in account.champions.values() if wanted in c.name.casefold()}
    exact = {name for name in names if name.casefold() == wanted}

    match sorted(exact or names):
        case []:
            return Unmatched(text, "no champion matches")

        case [name]:
            copies = [c for c in account.champions.values() if c.name == name]
            return max(copies, key=lambda c: (c.grade, c.awakening, c.level))

        case several:
            shown = ", ".join(several[:SHOWN_MATCHES])
            more = "…" if len(several) > SHOWN_MATCHES else ""
            return Unmatched(text, f"matches {len(several)}: {shown}{more}")


def parse_wanted(keys: list[str], offered: list[Tag]) -> tuple[Tag, ...] | FormErrors:
    """The tags named (by `Tag.key`), in `offered`'s order, once each."""
    unknown = sorted(set(keys) - {tag.key for tag in offered})
    if unknown:
        return FormErrors([f"can't ask for {', '.join(unknown)}"])

    return tuple(tag for tag in offered if tag.key in keys)


def parse_gear(keys: list[str], offered: list[Gear]) -> tuple[Gear, ...] | FormErrors:
    """The gear named (by `Gear.key`, empty ones ignored), in `offered`'s order."""
    named = {key for key in keys if key}
    unknown = sorted(named - {gear.key for gear in offered})
    if unknown:
        return FormErrors([f"no such gear: {', '.join(unknown)}"])

    return tuple(gear for gear in offered if gear.key in named)


def parse_assumed(
    texts: list[str], account: Account, tags: list[Tag]
) -> tuple[tuple[Gear, ...], tuple[Assumed, ...]] | FormErrors:
    """What's assumed: for the team (as gear any champion wears) and for single champions."""
    by_key = {tag.key: tag for tag in tags}
    team: list[Gear] = []
    single: list[Assumed] = []
    errors = []

    for text in dict.fromkeys(t.strip() for t in texts if t.strip()):
        who, _, key = text.rpartition("@")
        tag = by_key.get(key)
        champion = account.champions.get(int(who)) if who.isdigit() else None
        if tag is None or (who and champion is None):
            errors.append(f"can't assume {text!r}")
        elif champion is None:
            team.append(assumed_gear(tag))
        else:
            single.append(Assumed(tag, champion))

    return FormErrors(errors) if errors else (tuple(team), tuple(single))


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


def parse_form(
    form: Mapping[str, str], champion: Champion, account: Account, errors: list[str]
) -> Champion:
    """The champion in the form asked for (their skills and base stats follow it)."""
    text = form.get("form", "0").strip() or "0"
    forms = len(account.tables.hero_forms.get(champion.type_id, ()))

    if not (text.isdigit() and int(text) < max(forms, 1)):
        errors.append(f"{champion.name} has no such form")
        return champion

    return replace(champion, form=int(text))


def parse_limits(form: Mapping[str, str], prefix: str, errors: list[str]) -> Stats:
    limits: Stats = {}

    for stat in Stat:
        field = f"{prefix}_{stat.name}"
        if not form.get(field, "").strip():
            continue

        value = parse_number(form, field, f"{prefix} {STAT_LABELS[stat]}", errors)
        limits[stat] = value / 100 if stat in PERCENT_STATS else value

    return limits


def parse_sets(form: Mapping[str, str], account: Account, errors: list[str]) -> dict[int, int]:
    """Rows are numbered however the page numbered them; reported by position."""
    minimums: dict[int, int] = {}
    numbers = [key.removeprefix("set_") for key in form if re.fullmatch(r"set_\d+", key)]

    for row, number in enumerate(numbers):
        if not (set_field := form.get(f"set_{number}", "").strip()):
            continue

        set_id = int(set_field) if set_field.isdigit() else -1
        if set_id not in account.tables.sets:
            errors.append(f"unknown set in row {row + 1}")
            continue

        pieces = parse_number(form, f"pieces_{number}", f"pieces in set row {row + 1}", errors)
        if not 1 <= pieces <= MAX_PIECES:
            errors.append(f"set row {row + 1}: pieces must be 1 to {MAX_PIECES}")

        minimums[set_id] = int(pieces)

    return minimums


def parse_ranking(
    form: Mapping[str, str], champion: Champion, account: Account, errors: list[str]
) -> tuple[Goal, ...]:
    """The goals given a priority, lowest number first (ties in the table's order, damage
    last)."""
    prioritised: list[tuple[float, int, Goal]] = []  # priority, then the table's order

    for order, stat in enumerate(Stat):
        field = f"rank_{stat.name}"
        if form.get(field, "").strip():
            priority = parse_number(form, field, f"priority {STAT_LABELS[stat]}", errors)
            prioritised.append((priority, order, stat))

    if form.get("rank_DAMAGE", "").strip():
        priority = parse_number(form, "rank_DAMAGE", "priority Damage", errors)

        if goal := parse_damage(form, champion, account, errors):
            prioritised.append((priority, len(Stat), goal))

    if not any(form.get(f"rank_{name}", "").strip() for name in [*Stat.__members__, "DAMAGE"]):
        errors.append("give at least one stat a priority")

    return tuple(goal for _, _, goal in sorted(prioritised, key=lambda entry: entry[:2]))


def parse_damage(
    form: Mapping[str, str], champion: Champion, account: Account, errors: list[str]
) -> DamageGoal | None:
    skill_field = form.get("damage_skill", "")
    skill_id = int(skill_field) if skill_field.isdigit() else None

    if skill_id not in account.tables.skills_of(champion):
        errors.append("choose one of the champion's skills to rank damage by")
        return None

    enemy_defence = parse_number(form, "enemy_def", "enemy DEF", errors, DEFAULT_ENEMY_DEF)
    skill = account.tables.skills[skill_id]

    match damage_goal(skill, champion, enemy_defence):
        case Unsupported(reason=reason):
            errors.append(f"can't rank {skill.name}'s damage: {reason}")
            return None

        case goal:
            return goal


def parse_number(
    form: Mapping[str, str], field: str, label: str, errors: list[str], default: float = 0
) -> float:
    if not (text := form.get(field, "").strip()):
        return default

    try:
        return float(text)
    except ValueError:
        errors.append(f"{label}: {text!r} is not a number")
        return default
