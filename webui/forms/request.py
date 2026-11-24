"""
request.py - the request form's fields into a `Request`, or the reasons they can't be one.

Fields: `min_<STAT>`/`max_<STAT>` (C.RATE and C.DMG in %), `set_<n>` with `pieces_<n>` (any
number of rows, any `n`), `rank_<STAT>` (a priority, 1 first), `rank_DAMAGE` with
<<<<<<< Updated upstream
`damage_skill` (skill id) and `enemy_def`, `slack` (%), `builds`, the gear filters (each
=======
`damage_skill` (skill id) and `enemy_def`, the rates against an opponent (`enemy_res` and
`enemy_acc`, the target's unless typed): `rank_LANDS` and `rank_RESISTS` (debuffs landing
against its RES, resisting its ACC), `min_landing` and `min_resisting` (%: minimums, turned into
ACC's and RES's; a ranked rate's is its target instead, ranked up to and not held to), `slack`
(%), `builds`, the gear filters (each
>>>>>>> Stashed changes
present when ticked: `unworn_only`; `locked` with `lock_level`; `exclude_<rule key>` per
reserve rule), `above_level`, `form` (which of a mythical's forms, 0 first; absent: the first).
The equip and preview buttons post `artifact_ids`, comma-separated.

- `MAX_BUILDS`, `DEFAULT_ENEMY_DEF`, `DEFAULT_ABOVE_LEVEL`: the form's shape
- `parse_request` (`parse_gear_filter`, `exclude_field`): the boundary
<<<<<<< Updated upstream
- `parse_form`, `parse_limits`, `parse_sets`, `parse_ranking`, `parse_damage`: its steps
=======
- `RATE_GOALS`, `RATE_FIELDS`: the rates' rank fields, and their % and opponent's
- `parse_form`, `parse_limits`, `parse_rate_minimums`, `parse_sets`, `parse_ranking`,
  `parse_damage`, `parse_rate`, `parse_opponent`, `parse_battle` (`parse_buffs`,
  `parse_leader`): its steps
>>>>>>> Stashed changes
- `parse_equip`: the build buttons' pieces
"""

import re
from collections.abc import Mapping
from dataclasses import replace

from optimiser.account import LOCK_LEVELS, Account, Champion, Locks, Stat, Stats
from optimiser.damage import DamageGoal, Unsupported, damage_goal
from optimiser.labels import PERCENT_STATS, STAT_LABELS
from optimiser.reserve import Rule, reservations, rule_key
from optimiser.solve import MAX_PIECES, GearFilter, Goal, Request
from webui.forms.common import FormErrors, parse_number

DEFAULT_ENEMY_DEF = 6000
<<<<<<< Updated upstream
=======
RATE_GOALS = {"LANDS": "Debuffs landing", "RESISTS": "Resisting debuffs"}
RATE_FIELDS = {  # each rate's % field, its label, and the opponent's stat it's against
    "LANDS": ("min_landing", "lands at least", "enemy_res"),
    "RESISTS": ("min_resisting", "resists at least", "enemy_acc"),
}
>>>>>>> Stashed changes
DEFAULT_ABOVE_LEVEL = 8
MAX_BUILDS = 10


def parse_request(
    form: Mapping[str, str],
    champion: Champion,
    account: Account,
    locks: Locks,
    rules: tuple[Rule, ...],
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
    gear = parse_gear_filter(form, account, locks, rules, errors)

    if not 0 <= slack <= 50:
        errors.append("slack must be between 0 and 50 %")

    if not 1 <= builds <= MAX_BUILDS:
        errors.append(f"builds must be between 1 and {MAX_BUILDS}")

    if errors:
        return FormErrors(errors)

    return Request(
        champion=champion,
        minimums=minimums,
        maximums=maximums,
        set_minimums=set_minimums,
        ranking=ranking,
        slack=slack / 100,
        builds=int(builds),
        gear=gear,
        above_level=int(above_level),
    )


def exclude_field(rule: Rule) -> str:
    """The gear filter's field keeping out what `rule` reserves."""
    return f"exclude_{rule_key(rule)}"


def parse_gear_filter(
    form: Mapping[str, str],
    account: Account,
    locks: Locks,
    rules: tuple[Rule, ...],
    errors: list[str],
) -> GearFilter:
    level = form.get("lock_level", "0")

    if "locked" in form and not (level.isdigit() and int(level) < max(LOCK_LEVELS)):
        errors.append(f"lock level must be 0 to {max(LOCK_LEVELS) - 1}")

    excluded = tuple(rule for rule in rules if exclude_field(rule) in form)
    return GearFilter(
        unworn_only="unworn_only" in form,
        lock_level=int(level) if "locked" in form and level.isdigit() else None,
        locks=locks,
        rules=excluded,
        reserved=reservations(account, excluded),
    )


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


<<<<<<< Updated upstream
=======
def parse_rate_minimums(form: Mapping[str, str], errors: list[str]) -> Stats:
    """The rates asked at least and not ranked, as the ACC and RES they take (each at least the
    stat's own minimum, if one's typed too). A ranked rate's % is its target instead."""
    limits: Stats = {}

    for name in RATE_GOALS:
        if form.get(f"rank_{name}", "").strip() or not form.get(RATE_FIELDS[name][0], "").strip():
            continue

        if (rate := parse_rate(form, name, errors)) is None or rate.target is None:
            continue

        if (least := rate.least_for(rate.target)) is not None:
            typed = parse_number(form, f"min_{rate.stat.name}", "", [], default=0)
            limits[rate.stat] = max(float(least), typed)

    return limits


>>>>>>> Stashed changes
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


<<<<<<< Updated upstream
=======
def parse_rate(form: Mapping[str, str], name: str, errors: list[str]) -> Lands | Resists | None:
    """The rate against the opponent, its % (if typed) its target."""
    percent_field, label, opponent_field = RATE_FIELDS[name]
    opponent = parse_opponent(form, opponent_field, errors)
    target = None

    if form.get(percent_field, "").strip():
        target = parse_number(form, percent_field, label, errors) / 100

    if opponent is None:
        return None

    rate = Lands(opponent, target) if name == "LANDS" else Resists(opponent, target)
    if target is not None and rate.least_for(target) is None:
        stat = STAT_LABELS[rate.stat]
        errors.append(f"{label} {target:.0%}: no {stat} gets there (3-97 %)")
        return None

    return rate


def parse_opponent(form: Mapping[str, str], field: str, errors: list[str]) -> float | None:
    """The opponent's RES (`enemy_res`) or ACC (`enemy_acc`): needed for a rate."""
    label = "the opponent's RES" if field == "enemy_res" else "the opponent's ACC"

    if not form.get(field, "").strip():
        message = f"a rate needs {label}: pick a target, or type it"
        if message not in errors:
            errors.append(message)

        return None

    value = parse_number(form, field, label, errors)
    return value if value >= 0 else None


def parse_battle(
    form: Mapping[str, str], champion: Champion, account: Account, errors: list[str]
) -> Battle:
    return Battle(parse_buffs(form, errors), parse_leader(form, champion, account, errors))


def parse_buffs(form: Mapping[str, str], errors: list[str]) -> tuple[Buff, ...]:
    buffs = []

    for stat, strengths in BUFFS.items():
        if not (text := form.get(f"buff_{stat.name}", "").strip()):
            continue

        if buff := next((b for b in strengths if str(b.percent) == text), None):
            buffs.append(buff)
        else:
            shown = " or ".join(str(b.percent) for b in strengths)
            errors.append(f"an Increase {STAT_LABELS[stat]} buff is {shown} %, not {text}")

    return tuple(buffs)


def parse_leader(
    form: Mapping[str, str], champion: Champion, account: Account, errors: list[str]
) -> Leader | None:
    if not (key := form.get("aura", "").strip()):
        return None

    offered = auras_reaching(account, champion)

    if leader := next((each for each in offered if each.key == key), None):
        return leader

    errors.append(f"that aura no longer reaches {champion.name}: pick another leader")
    return None


>>>>>>> Stashed changes
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
