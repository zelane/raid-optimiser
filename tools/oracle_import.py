"""Turn raider's base-stat oracle output into tables for the optimiser.

    uv run python -m tools.oracle_import /tmp/raider-oracle.json data/game/hero_types.json data/game

Writes:
  base_stats_6_60.json  {type_id: [stats per form]} exact in-game base stats at 6* L60
  level_curve.json      {grade: {level: multiplier}} for ATK/DEF (HP = static*15*m),
                        median across sample types; for champions below 6* L60
Stats use the game's units (crit as fractions, e.g. 0.15).
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

import click


@click.command(help=__doc__)
@click.argument("oracle_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("types_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("out_dir", type=click.Path(file_okay=False))
def main(oracle_path: str, types_path: str, out_dir: str) -> None:
    rows = json.load(open(oracle_path))["rows"]
    types = {t["id"]: t for t in json.load(open(types_path))}
    out = Path(out_dir)

    top = defaultdict(dict)
    curve = defaultdict(list)
    for r in rows:
        stats = {k: round(v, 6) for k, v in r["base"].items()}
        if (r["grade"], r["level"]) == (6, 60):
            top[r["type_id"]][r["form"]] = stats
        static = types[r["type_id"]]["forms"][r["form"]]["base_stats"]
        for k in ("Attack", "Defence"):
            if static.get(k):
                curve[(r["grade"], r["level"])].append(r["base"][k] / static[k])

    base = {tid: [forms[f] for f in sorted(forms)] for tid, forms in sorted(top.items())}
    json.dump(base, open(out / "base_stats_6_60.json", "w"), indent=1)

    table = defaultdict(dict)
    worst = 0.0
    for (g, lvl), ms in sorted(curve.items()):
        if len(ms) < 3:  # only the 6* L60 point has thousands; grid points have ~12
            continue
        med = statistics.median(ms)
        table[g][lvl] = round(med, 5)
        if (g, lvl) != (6, 60):
            worst = max(worst, max(abs(m / med - 1) for m in ms))
    json.dump(table, open(out / "level_curve.json", "w"), indent=1)
    print(f"{len(base)} types at 6*60 -> {out / 'base_stats_6_60.json'}")
    print(
        f"{sum(len(v) for v in table.values())} grade/level points -> {out / 'level_curve.json'} "
        f"(max deviation across sample types {worst:.2%})"
    )


if __name__ == "__main__":
    main()
