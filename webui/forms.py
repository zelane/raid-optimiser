"""
forms.py - the request form's fields into a `Request`, or the reasons they can't be one.
The boundary: past here the solver sees only valid, typed requests.

Fields: `min_<STAT>`/`max_<STAT>` (C.RATE and C.DMG in %), `set_<n>` with `pieces_<n>`,
`rank_<STAT>` (a priority, 1 first), `rank_DAMAGE` with `damage_skill` (skill id) and
`enemy_def`, `slack` (%), `builds`, `pool` (a `pool_name`), `above_level`. The equip button
posts `artifact_ids`, comma-separated; the champion list's lock picker posts `level`.

- `SET_ROWS`, `MAX_BUILDS`, `DEFAULT_ENEMY_DEF`, `DEFAULT_ABOVE_LEVEL`: the form's shape
- `FormErrors`: what's wrong with a submitted form
- `parse_request`: the boundary
- `parse_equip`: the equip button's pieces
- `parse_lock`: the lock picker's level
- `parse_limits`, `parse_sets`, `parse_ranking`, `parse_damage`, `parse_number`: its steps
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account, Champion, Stat, Stats
from optimiser.damage import DamageGoal, Unsupported, damage_goal
from optimiser.labels import PERCENT_STATS, STAT_LABELS, parse_pool
from optimiser.solve import Goal, Request
from optimiser.store import LOCK_LEVELS, Locks

SET_ROWS = 3
MAX_PIECES = 9  # one per slot
DEFAULT_ENEMY_DEF = 6000
DEFAULT_ABOVE_LEVEL = 8
MAX_BUILDS = 10


@dataclass(frozen=True)
class FormErrors:
    messages: list[str]


def parse_request(
    form: Mapping[str, str], champion: Champion, account: Account, locks: Locks
) -> Request | FormErrors:
    errors: list[str] = []
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
    minimums: dict[int, int] = {}

    for row in range(SET_ROWS):
        if not (set_field := form.get(f"set_{row}", "").strip()):
            continue

        set_id = int(set_field) if set_field.isdigit() else -1
        if set_id not in account.tables.sets:
            errors.append(f"unknown set in row {row + 1}")
            continue

        pieces = parse_number(form, f"pieces_{row}", f"pieces in set row {row + 1}", errors)
        if not 1 <= pieces <= 9:
            errors.append(f"set row {row + 1}: pieces must be 1 to 9")

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

    if skill_id not in account.tables.hero_skills.get(champion.type_id, ()):
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
