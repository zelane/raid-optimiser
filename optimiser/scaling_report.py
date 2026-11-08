"""
scaling_report.py - which 6★ champions (each form apart) may need an exception in
`optimiser.scaling.OVERRIDES`: what each pulls on, the type it gets, and the flags worth a
look. The champion-exceptions skill (`.claude/skills/champion-exceptions`) works from it.

    uv run python -m optimiser.scaling_report            # flagged forms only
    uv run python -m optimiser.scaling_report --all      # every form
    uv run python -m optimiser.scaling_report --name Kurosa

- `Flag`, `FLAG_NOTES`, `Row`: a form, as the report shows it
- `report`: the rows
- `flags_for`, `formulas_of`, `describe_pull`, `print_row`, `main`: its steps
"""

import argparse
import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from optimiser.account import Account, load_account
from optimiser.labels import STAT_LABELS
from optimiser.scaling import (
    OVERRIDES,
    TOKENS,
    Wearer,
    evaluate,
    wearer_pull,
    wearer_type,
    wearers,
)

ROOT = Path(__file__).resolve().parents[1]
UTILITY = ("ACC", "RES", "SPD")
TARGET_TERMS = re.compile(r"TRG_|REL_|target|Counter|Count\(|relic|CALCULATED|HP_PERC")


class Flag(StrEnum):
    UNREADABLE = "unreadable"
    TARGET = "target-dependent"
    UTILITY = "utility stat"
    NO_SUPPORT_FORMULA = "support, nothing scales"
    FORMS_DIFFER = "forms differ"
    OWN_TYPE = "own type"
    OVERRIDDEN = "overridden"


FLAG_NOTES = {
    Flag.UNREADABLE: "a formula couldn't be evaluated, so its pull is missing",
    Flag.TARGET: "a formula reads the target or the battle; only the caster's stats count",
    Flag.UTILITY: "ACC, RES or SPD appears in a formula",
    Flag.NO_SUPPORT_FORMULA: "a Support whose heals/shields don't scale: standard support",
    Flag.FORMS_DIFFER: "a mythical whose forms get different types: is one the geared form?",
    Flag.OWN_TYPE: "gets a type of its faction's own",
    Flag.OVERRIDDEN: "has an entry in OVERRIDES",
}


@dataclass(frozen=True)
class Row:
    name: str
    faction: str
    role: str
    damage: str  # "ATK 1, HP 0.4"
    support: str
    type_label: str  # its own type, or "standard"
    flags: tuple[Flag, ...]
    formulas: tuple[str, ...]  # "Skill: kind formula"


def report(account: Account) -> list[Row]:
    forms = wearers(account)
    types = {(w.champion.name, w.form_number): wearer_type(w, account) for w in forms}
    rows = []

    for wearer in forms:
        own = types[(wearer.champion.name, wearer.form_number)]
        pull = wearer_pull(wearer, account)
        rows.append(
            Row(
                name=wearer.name(),
                faction=wearer.champion.faction,
                role=wearer.form.role,
                damage=describe_pull(pull.damage),
                support=describe_pull(pull.support),
                type_label=own.label if own else "standard",
                flags=flags_for(wearer, account, pull.support, own is not None, types),
                formulas=tuple(
                    dict.fromkeys(f"{label}: {f}" for label, f in formulas_of(wearer, account))
                ),
            )
        )

    return rows


def flags_for(wearer: Wearer, account: Account, support, has_own, types) -> tuple[Flag, ...]:
    formulas = [formula for _, formula in formulas_of(wearer, account)]
    stats = {stat: 1000.0 for stat in TOKENS.values()}
    tokens = {token for formula in formulas for token in re.findall(r"[A-Z_]+", formula)}
    siblings = {
        own.key if own else None for (name, _), own in types.items() if name == wearer.champion.name
    }
    checks = (
        (Flag.UNREADABLE, any(evaluate(f, stats) is None for f in formulas)),
        (Flag.TARGET, any(TARGET_TERMS.search(f) for f in formulas)),
        (Flag.UTILITY, any(token in UTILITY for token in tokens)),
        (Flag.NO_SUPPORT_FORMULA, wearer.form.role == "Support" and not support),
        (Flag.FORMS_DIFFER, wearer.forms > 1 and len(siblings) > 1),
        (Flag.OWN_TYPE, has_own),
        (Flag.OVERRIDDEN, (wearer.champion.name, wearer.form_number) in OVERRIDES),
    )
    return tuple(flag for flag, applies in checks if applies)


def formulas_of(wearer: Wearer, account: Account) -> Iterator[tuple[str, str]]:
    """(where it's from: "Skill" or "Skill, Heal", the formula)"""
    for skill_id in wearer.form.skills:
        if (skill := account.tables.skills.get(skill_id)) is None:
            continue

        yield from ((skill.name, hit.formula) for hit in skill.hits)
        yield from ((f"{skill.name}, {e.kind}", e.formula) for e in skill.scaling)


def describe_pull(pull) -> str:
    ordered = sorted(pull.items(), key=lambda item: -item[1])
    return ", ".join(f"{STAT_LABELS[stat]} {share:.2g}" for stat, share in ordered) or "-"


def print_row(row: Row) -> None:
    flags = ", ".join(row.flags) or "-"
    print(f"{row.name}  [{row.faction}, {row.role}]  -> {row.type_label}  flags: {flags}")
    print(f"    damage: {row.damage}    support: {row.support}")

    for formula in row.formulas:
        print(f"      {formula}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Champions that may need a scaling exception")
    parser.add_argument("--all", action="store_true", help="every form, not just flagged ones")
    parser.add_argument("--name", help="only champions whose name contains this")
    args = parser.parse_args()

    account = load_account(
        ROOT / "captures" / "latest", ROOT / "static", ROOT / "schema" / "schema.json"
    )
    interesting = {Flag.UNREADABLE, Flag.UTILITY, Flag.FORMS_DIFFER, Flag.OWN_TYPE}
    interesting |= {Flag.OVERRIDDEN}

    for row in report(account):
        if args.name and args.name.lower() not in row.name.lower():
            continue

        if args.all or args.name or interesting & set(row.flags):
            print_row(row)

    print()

    for flag, note in FLAG_NOTES.items():
        print(f"{flag}: {note}")


if __name__ == "__main__":
    main()
