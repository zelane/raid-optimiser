"""
result.py - what the web UI's calls into the outside world (the extractor's proxy, the memory
reader) return: an outcome, or why it failed.

- `Err`, `Result`, `failed`: the outcome
"""

from dataclasses import dataclass
from typing import TypeIs


@dataclass(frozen=True)
class Err:
    reason: str


type Result[T] = T | Err


def failed[T](result: Result[T]) -> TypeIs[Err]:
    return isinstance(result, Err)
