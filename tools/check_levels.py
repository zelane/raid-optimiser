"""Check optimiser/levels.py (base stats by rank and level) against the game.

    python3 -I tools/check_levels.py metadata <global-metadata.dat>
    python3 -I tools/check_levels.py oracle <base_stats_6_60.json> data/game/hero_types.json

metadata: the game's level multipliers (`BattleStats.Multipliers`) must still be in the
metadata byte for byte; update-static.sh runs this after a game update. If they've moved,
re-dump the game and read the table again (the field initialiser's "Metadata offset" in
dump.cs, from `BattleStats..cctor`'s `InitializeArray`).

oracle: compare the formula with base stats the raider oracle read from the running game
({type_id: [stats per form]} at 6* L60, as tools/oracle_import.py wrote them).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from optimiser.account import STAT_NAMES  # noqa: E402
from optimiser.levels import MULTIPLIERS_BLOB, base_stats  # noqa: E402

TOLERANCE = 1e-6  # the oracle's values are rounded to 6 places (crit: Fixed division)


def check_metadata(path: Path) -> int:
    data = path.read_bytes()
    at = data.find(MULTIPLIERS_BLOB)

    if at < 0:
        print(f"level multipliers not found in {path}: the game changed its level curve", file=sys.stderr)
        return 1

    print(f"level multipliers unchanged (metadata offset {at:#x})")
    return 0


def check_oracle(oracle_path: Path, types_path: Path) -> int:
    oracle = json.loads(oracle_path.read_text())
    types = {t["id"]: t for t in json.loads(types_path.read_text())}
    checked, wrong = 0, []

    for type_id, forms in oracle.items():
        hero = types.get(int(type_id))
        if hero is None:
            continue
        for number, expected in enumerate(forms):
            unscaled = {
                STAT_NAMES[k]: v for k, v in hero["forms"][number]["base_stats"].items() if k in STAT_NAMES
            }
            got = base_stats(unscaled, 6, 60)
            checked += 1
            diff = {
                k: (v, got[STAT_NAMES[k]])
                for k, v in expected.items()
                if k in STAT_NAMES and abs(v - got[STAT_NAMES[k]]) > TOLERANCE
            }
            if diff:
                wrong.append((hero["name"], type_id, number, diff))

    for name, type_id, number, diff in wrong[:20]:
        print(f"{name} ({type_id} form {number}): " + ", ".join(f"{k} oracle {a} formula {b}" for k, (a, b) in diff.items()))
    print(f"{checked - len(wrong)}/{checked} forms exact")
    return 1 if wrong else 0


def main() -> int:
    match sys.argv[1:]:
        case ["metadata", path]:
            return check_metadata(Path(path))
        case ["oracle", oracle, types]:
            return check_oracle(Path(oracle), Path(types))
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
