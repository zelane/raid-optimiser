"""Turn the game's cached static data into named, typed JSON using a dump-derived schema.

    uv run python -m tools.static_export <static-data dir or file> schema/schema.json out/ [--full]

The cache (`LocalLow/Plarium/Raid_ Shadow Legends/static-data`) is decoded by
`tools.static_decode`; given the directory, its newest file is read.

Writes out/{sets,hero_types,bonuses,skills,glyphs,gear,enemies,effect_sources,items,
shards,levelling,loot}.json (and out/static.json with --full).
Its parts: `static_convert` (the schema's names and types), `static_tables` (sets, champion
types, bonuses, gear, glyphs, items, shards, levelling, effect sources), `static_skills` (skills,
and whether they reach a boss) and `static_stages` (enemies, stages, loot).

Exits non-zero if validation fails, which usually means the schema came from a dump
older than the game version: run `just update`.
"""

import json
import sys
from pathlib import Path

import click

from tools.static_convert import Converter
from tools.static_decode import decode, newest
from tools.static_skills import build_skills
from tools.static_stages import build_enemies, build_loot
from tools.static_tables import (
    build_bonuses,
    build_effect_sources,
    build_gear,
    build_glyphs,
    build_hero_types,
    build_items,
    build_levelling,
    build_sets,
    build_shards,
    source_skill_ids,
)


def fmt_pct(x):
    p = x * 100
    return f"{p:g}%" if abs(p - round(p)) > 1e-9 else f"{round(p)}%"


def validate(sets, heroes, conv):
    errors = []
    bad_names = [s["id"] for s in sets if not s["name"] or s["name"].startswith("l10n:")]
    if bad_names:
        errors.append(f"sets without resolved names: {bad_names}")
    # Every fixed stat bonus should appear in the human-readable description.
    mismatched = []
    for s in sets:
        if s["variable"] or not s["description"] or s["placeholder_text"]:
            continue
        for st in s["tiers"][0]["stats"]:
            if st["stat"] == "IgnoreDefence":
                continue
            want = f"{st['value']:g}" if st["absolute"] else fmt_pct(st["value"])
            if want not in s["description"]:
                mismatched.append(f"{s['name']}: {want} not in {s['description']!r}")
    if mismatched:
        errors.append("set bonuses disagree with descriptions:\n    " + "\n    ".join(mismatched))
    playable = [h for h in heroes if h["forms"]]
    named = sum(1 for h in playable if h["name"] and not h["name"].startswith("l10n:"))
    if not playable or named / len(playable) < 0.9:
        errors.append(f"only {named}/{len(playable)} hero types have names")
    no_stats = sum(1 for h in playable if not h["forms"][0]["base_stats"].get("Health"))
    if no_stats > len(playable) * 0.05:
        errors.append(f"{no_stats}/{len(playable)} hero types have no base HP")
    # Unknown keys in the records we read mean their layout changed: fail. New keys in
    # the container classes (new sections/fields we don't use) only warrant a warning.
    strict = {
        "ArtifactSetInfo",
        "ArtifactSubSetInfo",
        "StatBonus",
        "HeroType",
        "HeroForm",
        "BattleStats",
    }
    drift = {f"{c}.{k}": n for (c, k), n in conv.unknown_keys.items() if c in strict}
    if drift:
        errors.append(f"keys missing from schema in records we read: {drift}")
    return errors


@click.command(help=__doc__)
@click.argument("static_data", type=click.Path(exists=True, path_type=Path))
@click.argument("schema_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("out_dir", type=click.Path(file_okay=False))
@click.option("--full", is_flag=True, help="Also write the whole named static.json (~100MB).")
def main(static_data: Path, schema_path: str, out_dir: str, full: bool) -> None:
    source = newest(static_data) if static_data.is_dir() else static_data
    print(f"static data {source.parent.name} ({source.stat().st_size} bytes)")
    raw = decode(source)
    schema = json.load(open(schema_path))
    conv = Converter(schema, raw.get("ca") or {})
    data = conv.conv({k: v for k, v in raw.items() if k not in ("ca", "ccl")}, "StaticData")
    assert isinstance(data, dict)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    skills = {s["Id"]: s for s in data["SkillData"]["SkillTypes"]}
    sets = build_sets(data["ArtifactData"], skills)
    heroes = build_hero_types(data["HeroData"])
    status_names = schema["enums"]["StatusEffectTypeId"]
    sources = build_effect_sources(data)
    json.dump(sources, open(out / "effect_sources.json", "w"), indent=1, ensure_ascii=False)
    built = build_skills(skills, heroes, status_names, source_skill_ids(sources))
    json.dump(built, open(out / "skills.json", "w"), ensure_ascii=False)
    json.dump(sets, open(out / "sets.json", "w"), indent=1, ensure_ascii=False)
    json.dump(heroes, open(out / "hero_types.json", "w"), indent=1, ensure_ascii=False)
    bonuses = build_bonuses(data, raw.get("ca") or {})
    json.dump(bonuses, open(out / "bonuses.json", "w"), indent=1, ensure_ascii=False)
    gear = build_gear(data["ArtifactData"])
    json.dump(gear, open(out / "gear.json", "w"), indent=1, ensure_ascii=False)
    glyphs = build_glyphs(data["BlackMarketData"])
    json.dump(glyphs, open(out / "glyphs.json", "w"), indent=1, ensure_ascii=False)
    shards = build_shards(data["ShardData"])
    json.dump(shards, open(out / "shards.json", "w"), indent=1, ensure_ascii=False)
    loot = build_loot(data["StageData"], schema["enums"])
    json.dump(loot, open(out / "loot.json", "w"), indent=1)
    levelling = build_levelling(data["HeroData"], data["BlackMarketData"])
    json.dump(levelling, open(out / "levelling.json", "w"), indent=1)
    items = build_items(data["BlackMarketData"])
    json.dump(items, open(out / "items.json", "w"), indent=1, ensure_ascii=False)
    enemies = build_enemies(data, skills, schema["enums"])
    json.dump(enemies, open(out / "enemies.json", "w"), ensure_ascii=False)
    if full:
        json.dump(data, open(out / "static.json", "w"), ensure_ascii=False)

    print(f"{len(sets)} sets, {len(heroes)} hero types -> {out.resolve()}")
    if conv.unknown_keys:
        top = ", ".join(f"{c}.{k}" for (c, k), _ in conv.unknown_keys.most_common(8))
        print(f"note: {len(conv.unknown_keys)} keys not in schema (kept as '?key'), e.g. {top}")
        print("      (the dump predates this game version: just update)")
    for s in sets:
        if s["placeholder_text"]:
            print(f"note: set {s['id']} has placeholder text (unreleased?)")
    if conv.enum_misses:
        top = ", ".join(f"{e}={v}" for (e, v), _ in conv.enum_misses.most_common(8))
        print(f"note: {len(conv.enum_misses)} enum values not in schema, e.g. {top}")
    errors = validate(sets, heroes, conv)
    for e in errors:
        print(f"VALIDATION: {e}", file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
