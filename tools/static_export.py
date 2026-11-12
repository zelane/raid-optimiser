"""Turn raw game static data JSON into named, typed JSON using a dump-derived schema.

    python3 -I tools/static_export.py static-raw.json schema/schema.json out/ [--full]

Writes out/{sets,hero_types,bonuses,skills,glyphs,gear}.json (and out/static.json with --full).
Exits non-zero if validation fails, which usually means the schema came from a dump
older than the game version: re-dump and re-run tools/gen_schema.py.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

FIXED_ONE = 2**32  # SharedModel Fixed is 32.32 fixed point
PRIMITIVES = {"int", "uint", "long", "ulong", "short", "ushort", "byte", "sbyte",
              "double", "float", "bool", "string", "decimal", "Int32", "Int64"}
LIST_RE = re.compile(r"^(?:List|IReadOnlyList|IList|IEnumerable|HashSet|IReadOnlyCollection|ICollection)<(.+)>$")


def split_args(s):
    depth, cur, out = 0, "", []
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()]


class Converter:
    def __init__(self, schema, strings):
        self.classes, self.enums, self.strings = schema["classes"], schema["enums"], strings
        self.unknown_keys = Counter()   # (class, key) present in data, absent from schema
        self.enum_misses = Counter()    # (enum, value) not in schema
        self.unresolved_text = 0

    def conv(self, v, t):
        if v is None:
            return None
        t = t.strip().replace("System.", "")
        if t.endswith("?"):
            t = t[:-1]
        if t.startswith("Nullable<"):
            return self.conv(v, t[9:-1])
        if t.endswith("[]"):
            return [self.conv(x, t[:-2]) for x in v] if isinstance(v, list) else v
        m = LIST_RE.match(t)
        if m:
            return [self.conv(x, m.group(1)) for x in v] if isinstance(v, list) else v
        if t.startswith(("Dictionary<", "IReadOnlyDictionary<", "SortedDictionary<")) and isinstance(v, dict):
            kt, vt = split_args(t[t.index("<") + 1:-1])
            return {str(self.conv_key(k, kt)): self.conv(x, vt) for k, x in v.items()}
        short = t.split(".")[-1]
        if short in PRIMITIVES:
            return v
        if short == "Fixed":
            return v / FIXED_ONE if isinstance(v, (int, float)) else v
        if short == "SharedLTextKey" and isinstance(v, dict):
            text = self.strings.get(v.get("k")) or v.get("d")
            if not text or text.startswith("l10n:"):
                self.unresolved_text += 1
            return text
        if short in self.enums:
            return self.enum_name(short, v)
        cls = self.classes.get(short)
        if cls is not None and isinstance(v, dict):
            out = {}
            for k, x in v.items():
                f = cls.get(k)
                if f is None:
                    self.unknown_keys[(short, k)] += 1
                    out["?" + k] = x
                else:
                    out[f["name"]] = self.conv(x, f["type"])
            return out
        return v  # unknown/polymorphic type: keep raw

    def conv_key(self, k, kt):
        short = kt.split(".")[-1]
        if short in self.enums:
            return self.enum_name(short, int(k) if str(k).lstrip("-").isdigit() else k)
        return k

    def enum_name(self, enum, v):
        name = self.enums[enum].get(str(v))
        if name is None:
            self.enum_misses[(enum, v)] += 1
            return v
        return name


def stat_list(bonuses):
    return [{"stat": b["StatKindId"], "value": round(b["Value"], 6), "absolute": b["IsAbsolute"]}
            for b in bonuses or [] if b]


IGNORE_FORMULA = re.compile(r"^\s*-\s*([\d.]+)\s*(\*\s*sameSkillCount)?\s*$")


def set_ignore_defence(bonus, skills):
    """A set skill's ignore-DEF effects (ChangeDefenceModifier passives), as positive
    fractions. `per_set`: stacks per set worn (Cruel); `aoe_only`: AoE skills only (Slayer)."""
    if not bonus:
        return []
    out = []
    for effect in skills[bonus["SkillTypeId"]]["Effects"] or []:
        if effect["KindId"] != "ChangeDefenceModifier":
            continue
        match = IGNORE_FORMULA.match(effect["MultiplierFormula"] or "")
        if not match:
            raise ValueError(f"unexpected ignore-DEF formula {effect['MultiplierFormula']!r}")
        out.append({"skill": bonus["SkillTypeId"], "value": float(match.group(1)),
                    "per_set": bool(match.group(2)),
                    "aoe_only": "relatedEffectIsAoe" in (effect.get("Condition") or "")})
    return out


def build_sets(art, skills):
    sets = []
    for s in art["SetInfos"]:
        variable = bool(s.get("SubSetInfos"))
        if variable:
            # Each sub-set lists the full bonus state at that piece count.
            tiers = [{"pieces": u["ArtifactCount"], "stats": stat_list(u.get("StatBonuses")),
                      "skill_bonus": u.get("SkillBonus") is not None,
                      "ignore_defence": set_ignore_defence(u.get("SkillBonus"), skills)}
                     for u in s["SubSetInfos"]]
        else:
            stats = stat_list(([s["StatBonus"]] if s.get("StatBonus") else []) + (s.get("StatBonuses") or []))
            tiers = [{"pieces": s["ArtifactCount"], "stats": stats, "skill_bonus": s.get("SkillBonus") is not None,
                      "ignore_defence": set_ignore_defence(s.get("SkillBonus"), skills)}]
        # Unreleased sets ship with developer placeholder strings instead of real text.
        placeholder = (s["Name"] or "").endswith("artifact set name")
        sets.append({"id": s["ArtifactSetKindId"], "name": s["Name"], "variable": variable,
                     "pieces": s["ArtifactCount"], "tiers": tiers, "description": s["Description"],
                     "placeholder_text": placeholder})
    return sets


def build_hero_types(hero):
    out = []
    for h in hero["HeroTypes"]:
        out.append({
            "id": h["Id"], "name": h["Name"], "fraction": h["Fraction"], "rarity": h["Rarity"],
            "avatar": avatar_name(h),
            "forms": [{"element": f["Element"], "role": f["Role"],
                       "skills": f.get("SkillTypeIds") or [],
                       "base_stats": {k: round(v, 6) for k, v in (f.get("BaseStats") or {}).items()}}
                      for f in h.get("Forms") or []],
        })
    return out


def avatar_name(h):
    """The portrait sprite the game shows: the first form's default (lowest id) skin's. Mostly the
    type id; old champions that were bosses first use their boss portraits (Big 'Un: 21090)."""
    forms = h.get("Forms") or []
    visuals = (forms[0].get("VisualInfosBySkinId") or {}) if forms else {}
    return visuals[min(visuals, key=int)]["AvatarName"] if visuals else None


def cumulative(levels):
    """Running totals of [{stat: {Value, IsAbsolute}}] (each stat keeps one unit)."""
    out, acc = [], {}
    for lvl in levels:
        for k, b in lvl.items():
            prev = acc.get(k, {"value": 0.0, "absolute": b["IsAbsolute"]})
            acc[k] = {"value": round(prev["value"] + b["Value"], 6), "absolute": b["IsAbsolute"]}
        out.append({k: dict(v) for k, v in acc.items()})
    return out


RANKS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6}


def build_glyphs(market):
    """Glyphs (the game's power-up stones, sold in the black market's item table): each
    stat, rank and rarity with its roll range. Percentages are fractions, as on gear.
    Stones with no stat (StatId 0) are left out."""
    glyphs = []
    for item in market["Items"]:
        g = item.get("PowerUpData")
        if not g or g["StatId"] not in STAT_KINDS:
            continue
        glyphs.append({"stat": g["StatId"], "absolute": g["IsAbsolute"],
                       "rank": RANKS[g["RankId"]], "rarity": g["Rarity"],
                       "min": round(g["MinValue"], 6), "max": round(g["MaxValue"], 6)})
    return sorted(glyphs, key=lambda g: (g["stat"], not g["absolute"], g["rank"], g["max"]))


def build_gear(art):
    """Gear stats by level: `primary` (main stat at levels 0..max_level, by rank) and
    `ascension` (the ascension bonus at ascension levels 1..rank, ranks 4-6), each per stat
    and the slots it applies to. Rarity doesn't change either."""
    def tables(infos):
        return [{"stat": i["StatKey"]["KindId"], "absolute": i["StatKey"]["IsAbsolute"],
                 "slots": i["ApplicableKindIds"],
                 "values": {RANKS[r]: [round(v, 6) for v in vs]
                            for r, vs in i["ValuesByLevelByRankId"].items()}}
                for i in infos]
    return {"max_level": art["MaxArtifactLevel"], "primary": tables(art["PrimaryBonusInfos"]),
            "ascension": tables(art["AscendBonusInfos"])}


STAT_KINDS = {"Health", "Attack", "Defence", "Speed", "Resistance", "Accuracy",
              "CriticalChance", "CriticalDamage"}


def build_bonuses(data, strings):
    """Non-gear stat bonuses. Percentages apply to base stats.

    great_hall[stat][level-1]: the bonus at each level (not cumulative). arena[league]: classic arena league bonus.
    relics: each type's stats unlock at opening_levels[i]; values[stat][level - opening].
    empower[rarity][level-1] and
    awakening[rarity][AwakenedGrade-1] are cumulative totals. empower_substitutes: for
    champions only obtainable once (hero type id, ascension 0), the type whose copies empower
    them instead of duplicates (`StaticAcademyEmpowerData.HeroRecipes`). Empower stacking was
    verified against the game's CalcEmpowerBonus; awakening stacking confirmed by the user.
    Ascension (0-6) is not here: it is the last digit of TypeId, and each ascended
    type has its own base stats (see base_stats_6_60.json).
    """
    village, academy = data["VillageData"], data["AcademyData"]["Empower"]
    great_hall = {k: [{"value": round(x["Value"], 6), "absolute": x["IsAbsolute"]} for x in v]
                  for k, v in village["CapitolBonusByStatKind"].items()}
    legendary = cumulative([x["Bonuses"] for x in academy["Bonuses"]])
    empower = {"Epic": cumulative([x["Bonuses"] for x in academy["EpicBonuses"]]),
               "Legendary": legendary, "Mythical": legendary}
    awakening = {}
    for rarity, grades in data["DoubleAscendData"]["BlessingStatsByRarity"].items():
        grades = sorted(grades, key=lambda g: g["Grade"])  # Stars1..Stars6
        awakening[rarity] = cumulative([g["StatBonusByKindId"] for g in grades])
    masteries = {}
    for mid, b in data["MasteryData"]["MasteryBonusById"].items():
        name = strings.get(f"l10n:skill/name?id={mid}#static")
        m = {"name": name, "stat": b["StatKindId"], "value": round(b["Value"], 6), "absolute": b["IsAbsolute"]}
        if b["StatKindId"] == -1:  # Lore of Steel: scales artifact set stat bonuses
            m = {"name": name, "set_bonus_multiplier": round(1 + b["Value"], 6)}
        masteries[mid] = m
    arena = {
        league["Id"]: {k: {"value": round(v, 6), "absolute": False}
                       for k, v in league["BattleBonuses"].items() if v}
        for league in data["ArenaData"]["LeagueInfos"]
    }
    relic_data = data["RelicData"]
    relics = {
        "opening_levels": relic_data["StatBonusOpeningLevels"],
        "values": {stat: [{"value": round(v["Value"], 6), "absolute": v["IsAbsolute"]} for v in levels]
                   for stat, levels in relic_data["StatValueByLevel"].items()},
        "types": {str(t["Id"]): {"name": t["Name"], "stats": t["StatsBonus"] or []}
                  for t in relic_data["RelicTypes"]},
    }
    substitutes = {str(k): v for k, v in academy["HeroRecipes"].items()}
    return {"great_hall": great_hall, "arena": arena, "relics": relics, "empower": empower, "awakening": awakening,
            "empower_substitutes": substitutes, "masteries": masteries}


ENEMY_TARGETS = {"Target", "AllEnemies", "Boss", "EnemyWithHighestStamina", "MostInjuredEnemy",
                 "RandomEnemy", "RandomEnemyWithMaxBuffsCount"}


# Effects other than damage whose size scales with the caster's stats: what heals, shields,
# revives and bombs scale off.
SCALING_KINDS = {"Heal", "ApplyBuff", "Revive", "ApplyDebuff"}
OWN_STATS = re.compile(r"(?<![A-Z_])(ATK|DEF|HP|ACC|RES|SPD)(?![A-Z_])")


def build_skills(skills, heroes):
    """The champions' skills: name, whether it's AoE, its unconditional damage hits (formula,
    count, the skill's own DEF modifier), the damage bonus each book adds, and the formulas of
    its other effects that scale with the caster's stats (`scaling`: kind and formula)."""
    wanted = {skill_id for h in heroes for f in h["forms"] for skill_id in f["skills"]}
    out = {}
    for skill_id in sorted(wanted):
        skill = skills.get(skill_id)
        if not skill:
            continue
        hits = [e for e in skill["Effects"] or []
                if e["KindId"] == "Damage" and not e.get("Condition")
                and (e.get("TargetParams") or {}).get("TargetType") in ENEMY_TARGETS]
        out[str(skill_id)] = {
            "name": skill["Name"], "group": skill["Group"], "cooldown": skill["Cooldown"],
            "aoe": any(e["TargetParams"]["TargetType"] == "AllEnemies" for e in hits),
            "hits": [{"formula": e["MultiplierFormula"], "count": e["Count"],
                      "defence_modifier": round((e.get("DamageParams") or {}).get("DefenceModifier") or 0, 6)}
                     for e in hits],
            # One entry per book, in order (level L has the first L-1); 0 for non-damage books.
            "book_damage": [round(b["Value"], 6) if b["SkillBonusType"] == "Attack" else 0
                            for b in skill.get("SkillLevelBonuses") or []],
            "scaling": [{"kind": e["KindId"], "formula": e["MultiplierFormula"]}
                        for e in skill["Effects"] or []
                        if e["KindId"] in SCALING_KINDS
                        and OWN_STATS.search(e.get("MultiplierFormula") or "")],
        }
    return out


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
    strict = {"ArtifactSetInfo", "ArtifactSubSetInfo", "StatBonus", "HeroType", "HeroForm", "BattleStats"}
    drift = {f"{c}.{k}": n for (c, k), n in conv.unknown_keys.items() if c in strict}
    if drift:
        errors.append(f"keys missing from schema in records we read: {drift}")
    return errors


def main(raw_path, schema_path, out_dir, full=False):
    raw = json.load(open(raw_path))
    schema = json.load(open(schema_path))
    conv = Converter(schema, raw.get("ca") or {})
    data = conv.conv({k: v for k, v in raw.items() if k not in ("ca", "ccl")}, "StaticData")
    assert isinstance(data, dict)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    skills = {s["Id"]: s for s in data["SkillData"]["SkillTypes"]}
    sets = build_sets(data["ArtifactData"], skills)
    heroes = build_hero_types(data["HeroData"])
    json.dump(build_skills(skills, heroes), open(out / "skills.json", "w"), ensure_ascii=False)
    json.dump(sets, open(out / "sets.json", "w"), indent=1, ensure_ascii=False)
    json.dump(heroes, open(out / "hero_types.json", "w"), indent=1, ensure_ascii=False)
    bonuses = build_bonuses(data, raw.get("ca") or {})
    json.dump(bonuses, open(out / "bonuses.json", "w"), indent=1, ensure_ascii=False)
    gear = build_gear(data["ArtifactData"])
    json.dump(gear, open(out / "gear.json", "w"), indent=1, ensure_ascii=False)
    glyphs = build_glyphs(data["BlackMarketData"])
    json.dump(glyphs, open(out / "glyphs.json", "w"), indent=1, ensure_ascii=False)
    if full:
        json.dump(data, open(out / "static.json", "w"), ensure_ascii=False)

    print(f"{len(sets)} sets, {len(heroes)} hero types -> {out.resolve()}")
    if conv.unknown_keys:
        top = ", ".join(f"{c}.{k}" for (c, k), _ in conv.unknown_keys.most_common(8))
        print(f"note: {len(conv.unknown_keys)} keys not in schema (kept as '?key'), e.g. {top}")
        print("      (the dump predates this game version; re-dump + tools/gen_schema.py to refresh)")
    for s in sets:
        if s["placeholder_text"]:
            print(f"note: set {s['id']} has placeholder text (unreleased?)")
    if conv.enum_misses:
        top = ", ".join(f"{e}={v}" for (e, v), _ in conv.enum_misses.most_common(8))
        print(f"note: {len(conv.enum_misses)} enum values not in schema, e.g. {top}")
    errors = validate(sets, heroes, conv)
    for e in errors:
        print(f"VALIDATION: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--full"]
    sys.exit(main(*args, full="--full" in sys.argv))
