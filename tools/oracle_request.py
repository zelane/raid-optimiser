"""Write the request file for raider's base-stat oracle.

    python3 -I tools/oracle_request.py static/hero_types.json /tmp/raider-oracle-request.txt

Lines are "type_id grade level form". Requests every hero type at 6* L60 (each
metamorph form), plus the full grade x level grid for one type per rarity so the
scaling curve can be fitted and checked.
"""

import json
import sys

MAX_FORMS = 2  # HeroMetamorphForm has First=0, Second=1


def main(types_path, out_path):
    types = [t for t in json.load(open(types_path)) if t["forms"]]
    lines = []
    for t in types:
        for form in range(min(len(t["forms"]), MAX_FORMS)):
            lines.append(f"{t['id']} 6 60 {form}")

    grid_types = {}
    for t in types:
        if t["name"] and not t["name"].startswith("l10n:"):
            grid_types.setdefault(t["rarity"], t)
    for t in grid_types.values():
        for grade in range(1, 7):
            for level in range(1, grade * 10 + 1):
                lines.append(f"{t['id']} {grade} {level} 0")

    with open(out_path, "w") as f:
        f.write("# type_id grade level form\n" + "\n".join(lines) + "\n")
    names = ", ".join(f"{t['name']} ({r})" for r, t in grid_types.items())
    print(f"{len(lines)} requests -> {out_path}; grid types: {names}")


if __name__ == "__main__":
    main(*sys.argv[1:])
