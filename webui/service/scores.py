"""
scores.py - accessory potentials kept on disk, so a piece is scored once: a new snapshot
rescores only the pieces that changed, and a restarted server none. Kept per scorer (the
types, their weights and the gear tables) and per version of the scoring code; the latest
`KEPT` scorers' scores are kept.

- `KEPT`, `SCORING_CODE`: what's kept, and what invalidates it
- `known_potentials`: a scorer's scores (`read_kept`, `scorer_key`)
- `keep_potentials`: keeps them (`write_kept`)
"""

import hashlib
import pickle
from pathlib import Path

from optimiser.accessories import potential, roles
from optimiser.accessories.potential import Piece, Potential, Scorer

KEPT = 4
SCORING_CODE = (Path(potential.__file__), Path(roles.__file__))

type Kept = dict[str, dict[Piece, Potential]]  # by scorer key, most recently kept last


def known_potentials(path: Path, scorer: Scorer) -> dict[Piece, Potential]:
    return read_kept(path).get(scorer_key(scorer), {})


def keep_potentials(path: Path, scorer: Scorer, potentials: dict[Piece, Potential]) -> None:
    """Replaces the scorer's scores with `potentials` (the current pieces only)."""
    kept = read_kept(path)
    key = scorer_key(scorer)
    kept.pop(key, None)
    kept[key] = potentials
    write_kept(path, dict(list(kept.items())[-KEPT:]))


def read_kept(path: Path) -> Kept:
    """Empty if there's nothing kept, or it's unreadable (written by other code)."""
    try:
        with path.open("rb") as file:
            kept = pickle.load(file)
    except (OSError, pickle.UnpicklingError, AttributeError, ImportError, EOFError, TypeError):
        return {}

    return kept if isinstance(kept, dict) else {}


def write_kept(path: Path, kept: Kept) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")

    with partial.open("wb") as file:
        pickle.dump(kept, file, protocol=pickle.HIGHEST_PROTOCOL)

    partial.replace(path)


def scorer_key(scorer: Scorer) -> str:
    digest = hashlib.sha256(repr((scorer.types, scorer.gear, scorer.glyphs)).encode())

    for source in SCORING_CODE:
        digest.update(source.read_bytes())

    return digest.hexdigest()
