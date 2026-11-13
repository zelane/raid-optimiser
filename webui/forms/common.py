"""
common.py - what every form shares.

- `FormErrors`: what's wrong with a submitted form
- `parse_number`: a numeric field, its error noted
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class FormErrors:
    messages: list[str]


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
