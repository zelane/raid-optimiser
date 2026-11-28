"""
static_tables.py - the game's plain tables, as `tools.static_export` writes them: sets
(`sets.json`), champion types (`hero_types.json`), Great Hall, masteries and the rest of the
bonuses (`bonuses.json`), gear (`gear.json`), glyphs, black market items, shards, levelling
and what sets and relics bring (`effect_sources.json`).

- `build_sets`, `build_hero_types`, `build_bonuses`, `build_gear`, `build_glyphs`,
  `build_items`, `build_shards`, `build_levelling`, `build_effect_sources`: a file each
- `source_skill_ids`: the skills sets and relics bring, for `static_skills`
- `stat_list`, `set_ignore_defence`, `set_damage_bonus`, `game_formula`, `aura`, `avatar_name`,
  `cumulative`: their steps
"""

import ast
import re

from optimiser.tables import faction_name


def stat_list(bonuses):
    return [
        {"stat": b["StatKindId"], "value": round(b["Value"], 6), "absolute": b["IsAbsolute"]}
        for b in bonuses or []
        if b
    ]


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
        out.append(
            {
                "skill": bonus["SkillTypeId"],
                "value": float(match.group(1)),
                "per_set": bool(match.group(2)),
                "aoe_only": "relatedEffectIsAoe" in (effect.get("Condition") or ""),
            }
        )
    return out


# The dealt-damage multipliers gear can count on: the owner's own hits on enemies, nothing
# else asked (Feral and Protection 9 count buffs and debuffs on the target, so they're out).
OWN_DAMAGE = "isOwnerProduceRelatedEffect&&!relationTargetIsAlly"


FORMULA_NAMES = {"DMG_MUL": 1.0, "HP_PERC": 1.0, "sameSkillCount": 1.0}


def set_damage_bonus(bonus, skills):
    """A set skill's extra damage on the owner's hits (ChangeDamageMultiplier passives), at
    full HP, as a fraction (Zeal: 0.12). `per_set`: stacks per set worn (Zeal's
    sameSkillCount), up to `cap` if the game caps it (Zeal: 0.36)."""
    if not bonus:
        return []
    out = []
    for effect in skills[bonus["SkillTypeId"]]["Effects"] or []:
        if effect["KindId"] != "ChangeDamageMultiplier" or effect.get("Condition") != OWN_DAMAGE:
            continue
        formula = effect["MultiplierFormula"] or ""
        cap = ((effect.get("ValueRange") or {}).get("MaxFormula")) or None
        out.append(
            {
                "skill": bonus["SkillTypeId"],
                "value": round(game_formula(formula, FORMULA_NAMES), 6),
                "per_set": "sameSkillCount" in formula,
                "cap": round(game_formula(cap, FORMULA_NAMES), 6) if cap else None,
            }
        )
    return out


def game_formula(text: str, names: dict[str, float]) -> float:
    """A game formula's value (C-style: &&, ||, !, comparisons, arithmetic) with these names;
    anything else in it is an error."""
    python = re.sub(r"!(?!=)", " not ", text.replace("&&", " and ").replace("||", " or "))
    tree = ast.parse(python, mode="eval")
    allowed = (
        ast.Expression,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.And,
        ast.Or,
        ast.Not,
        ast.USub,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed) or (isinstance(node, ast.Name) and node.id not in names):
            raise ValueError(f"unexpected game formula {text!r}")
    return float(eval(compile(tree, "<formula>", "eval"), {"__builtins__": {}}, dict(names)))


def build_sets(art, skills):
    sets = []
    for s in art["SetInfos"]:
        variable = bool(s.get("SubSetInfos"))
        if variable:
            # Each sub-set lists the full bonus state at that piece count.
            tiers = [
                {
                    "pieces": u["ArtifactCount"],
                    "stats": stat_list(u.get("StatBonuses")),
                    "skill_bonus": u.get("SkillBonus") is not None,
                    "ignore_defence": set_ignore_defence(u.get("SkillBonus"), skills),
                    "damage_bonus": set_damage_bonus(u.get("SkillBonus"), skills),
                }
                for u in s["SubSetInfos"]
            ]
        else:
            stats = stat_list(
                ([s["StatBonus"]] if s.get("StatBonus") else []) + (s.get("StatBonuses") or [])
            )
            tiers = [
                {
                    "pieces": s["ArtifactCount"],
                    "stats": stats,
                    "skill_bonus": s.get("SkillBonus") is not None,
                    "ignore_defence": set_ignore_defence(s.get("SkillBonus"), skills),
                    "damage_bonus": set_damage_bonus(s.get("SkillBonus"), skills),
                }
            ]
        # Unreleased sets ship with developer placeholder strings instead of real text.
        placeholder = (s["Name"] or "").endswith("artifact set name")
        sets.append(
            {
                "id": s["ArtifactSetKindId"],
                "name": s["Name"],
                "variable": variable,
                "pieces": s["ArtifactCount"],
                "tiers": tiers,
                "description": s["Description"],
                "placeholder_text": placeholder,
            }
        )
    return sets


def build_hero_types(hero):
    out = []
    for h in hero["HeroTypes"]:
        out.append(
            {
                "id": h["Id"],
                "name": h["Name"],
                "fraction": h["Fraction"],
                "rarity": h["Rarity"],
                "avatar": avatar_name(h),
                "forms": [
                    {
                        "element": f["Element"],
                        "role": f["Role"],
                        "skills": f.get("SkillTypeIds") or [],
                        "base_stats": {
                            k: round(v, 6) for k, v in (f.get("BaseStats") or {}).items()
                        },
                    }
                    for f in h.get("Forms") or []
                ],
                "auras": [aura(leader) for leader in h.get("LeaderSkills") or []],
            }
        )
    return out


def aura(leader):
    """A leader skill: a stat bonus for the team, held to battles in one area and to allies
    of one affinity, faction or rarity where those are set (None: any)."""
    return {
        "stat": leader["StatKindId"],
        "value": round(leader["Amount"], 6),
        "absolute": leader["IsAbsolute"],
        "area": leader["Area"],
        "element": leader["Element"],
        "faction": leader["Faction"],
        "rarity": leader["Rarity"],
    }


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
        glyphs.append(
            {
                "stat": g["StatId"],
                "absolute": g["IsAbsolute"],
                "rank": RANKS[g["RankId"]],
                "rarity": g["Rarity"],
                "min": round(g["MinValue"], 6),
                "max": round(g["MaxValue"], 6),
            }
        )
    return sorted(glyphs, key=lambda g: (g["stat"], not g["absolute"], g["rank"], g["max"]))


def build_items(market):
    """The black market's items' names by id (`SkillUpgradeItemRare`: "Rare Skill Tome"), for
    the prizes events list (`optimiser.events`). Items the game leaves unnamed are left out."""
    return {
        item["Id"]: item["Name"]
        for item in market["Items"]
        if item.get("Name") and not item["Name"].startswith("l10n:")
    }


def build_shards(shard_data):
    """Each shard type: its name, the affinities it summons, and its odds by rarity, with their
    mercy (past `mercy_after` shards without the rarity, `mercy_step` more chance each), as
    the reader writes a summon boost's (`optimiser.summons`)."""
    return [
        {
            "id": shard["Id"],
            "name": shard.get("Name") or shard["Id"],
            "elements": shard.get("ApplicableElements") or [],
            "rules": [
                {
                    "rarity": rule["Rarity"],
                    "chance": rule["Chance"],
                    "mercy_step": rule.get("ChanceIncreaseOnEachTry"),
                    "mercy_after": rule.get("ChanceIncreaseSummonNumber"),
                }
                for rule in shard.get("DropRules") or ()
            ],
        }
        for shard in shard_data["ShardTypes"]
    ]


def build_levelling(hero_data, market):
    """The XP each level takes, by grade (`HeroExperienceByKey`, keyed grade × 1000 + level: from
    that level to the next, so the top level is one past the last), and what a brew gives
    (`HeroLevelUpData`, alike for each affinity's: more on a champion of its own), for the
    Champion Training plan (`optimiser.levelling`)."""
    by_grade = {}
    for key, xp in sorted(hero_data["HeroExperienceByKey"].items(), key=lambda kv: int(kv[0])):
        by_grade.setdefault(f"Stars{int(key) // 1000}", []).append(xp)

    brew = next(
        item["HeroLevelUpData"] for item in market["Items"] if item["Id"] == "HeroLevelUpItemMagic"
    )
    return {"xp": by_grade, "brew": brew["Xp"], "matching": brew["XpOnCorrectElement"]}


def build_gear(art):
    """Gear stats by level: `primary` (main stat at levels 0..max_level, by rank) and
    `ascension` (the ascension bonus at ascension levels 1..rank, ranks 4-6), each per stat
    and the slots it applies to. Rarity doesn't change either. `required_grade`: the stars a
    champion needs before a slot opens (the accessories: Ring 4, Cloak 5, Banner 6)."""

    def tables(infos):
        return [
            {
                "stat": i["StatKey"]["KindId"],
                "absolute": i["StatKey"]["IsAbsolute"],
                "slots": i["ApplicableKindIds"],
                "values": {
                    RANKS[r]: [round(v, 6) for v in vs]
                    for r, vs in i["ValuesByLevelByRankId"].items()
                },
            }
            for i in infos
        ]

    return {
        "max_level": art["MaxArtifactLevel"],
        "primary": tables(art["PrimaryBonusInfos"]),
        "ascension": tables(art["AscendBonusInfos"]),
        "required_grade": {
            kind: int(grade.removeprefix("Stars"))
            for kind, grade in (art.get("RequiredHeroGradeByKindId") or {}).items()
        },
    }


STAT_KINDS = {
    "Health",
    "Attack",
    "Defence",
    "Speed",
    "Resistance",
    "Accuracy",
    "CriticalChance",
    "CriticalDamage",
}


def build_bonuses(data, strings):
    """Non-gear stat bonuses. Percentages apply to base stats.

    great_hall[stat][level-1]: the bonus at each level (not cumulative). arena[league]: classic
    arena league bonus.
    relics: each type's stats unlock at opening_levels[i]; values[stat][level - opening].
    empower[rarity][level-1] and
    awakening[rarity][AwakenedGrade-1] are cumulative totals. empower_substitutes: for
    champions only obtainable once (hero type id, ascension 0), the type whose copies empower
    them instead of duplicates (`StaticAcademyEmpowerData.HeroRecipes`). Empower stacking was
    verified against the game's CalcEmpowerBonus; awakening stacking confirmed by the user.
    mastery_types[id]: each mastery's row in its tree, 1 (the top) to 6 (Helmsmasher's), by its
    depth under `MasteryTypes`' parents, and its price in scrolls (`MasteryPointType` -> how
    many, kinds it doesn't take left out).
    Ascension (0-6) is not here: it is the last digit of TypeId, and each ascended
    type has its own base stats (see base_stats_6_60.json).
    """
    village, academy = data["VillageData"], data["AcademyData"]["Empower"]
    great_hall = {
        k: [{"value": round(x["Value"], 6), "absolute": x["IsAbsolute"]} for x in v]
        for k, v in village["CapitolBonusByStatKind"].items()
    }
    legendary = cumulative([x["Bonuses"] for x in academy["Bonuses"]])
    empower = {
        "Epic": cumulative([x["Bonuses"] for x in academy["EpicBonuses"]]),
        "Legendary": legendary,
        "Mythical": legendary,
    }
    awakening = {}
    for rarity, grades in data["DoubleAscendData"]["BlessingStatsByRarity"].items():
        grades = sorted(grades, key=lambda g: g["Grade"])  # Stars1..Stars6
        awakening[rarity] = cumulative([g["StatBonusByKindId"] for g in grades])
    masteries = {}
    for mid, b in data["MasteryData"]["MasteryBonusById"].items():
        name = strings.get(f"l10n:skill/name?id={mid}#static")
        m = {
            "name": name,
            "stat": b["StatKindId"],
            "value": round(b["Value"], 6),
            "absolute": b["IsAbsolute"],
        }
        if b["StatKindId"] == -1:  # Lore of Steel: scales artifact set stat bonuses
            m = {"name": name, "set_bonus_multiplier": round(1 + b["Value"], 6)}
        masteries[mid] = m
    parents = {t["Id"]: t["ParentIds"] or [] for t in data["MasteryData"]["MasteryTypes"]}

    def row(mid):
        return 1 + max((row(parent) for parent in parents[mid]), default=0)

    mastery_types = {
        t["Id"]: {"row": row(t["Id"]), "price": {k: n for k, n in t["Price"].items() if n}}
        for t in data["MasteryData"]["MasteryTypes"]
    }
    arena = {
        league["Id"]: {
            k: {"value": round(v, 6), "absolute": False}
            for k, v in league["BattleBonuses"].items()
            if v
        }
        for league in data["ArenaData"]["LeagueInfos"]
    }
    relic_data = data["RelicData"]
    relics = {
        "opening_levels": relic_data["StatBonusOpeningLevels"],
        "values": {
            stat: [{"value": round(v["Value"], 6), "absolute": v["IsAbsolute"]} for v in levels]
            for stat, levels in relic_data["StatValueByLevel"].items()
        },
        "types": {
            str(t["Id"]): {"name": t["Name"], "stats": t["StatsBonus"] or []}
            for t in relic_data["RelicTypes"]
        },
    }
    substitutes = {str(k): v for k, v in academy["HeroRecipes"].items()}
    return {
        "great_hall": great_hall,
        "arena": arena,
        "relics": relics,
        "empower": empower,
        "awakening": awakening,
        "empower_substitutes": substitutes,
        "masteries": masteries,
        "mastery_types": mastery_types,
    }


def build_effect_sources(data):
    """What else can bring buffs, debuffs and effects to a team: each artifact set's set
    skills (the pieces they take), and each relic type's skills, with those only a champion of
    one faction gets (by the factions' display names, `faction_name`), the relic skill level
    each relic level reaches (`relic_skill_levels`), and each relic stone type's skills
    (`relic_stones`, by type id). The skills are in skills.json."""
    sets = []
    for s in data["ArtifactData"]["SetInfos"]:
        tiers = [s] + (s.get("SubSetInfos") or [])
        skills = [
            {
                "pieces": t.get("ArtifactCount") or s["ArtifactCount"],
                "skill": t["SkillBonus"]["SkillTypeId"],
            }
            for t in tiers
            if t.get("SkillBonus")
        ]
        if skills:
            sets.append({"id": s["ArtifactSetKindId"], "name": s["Name"], "skills": skills})
    relics = []
    for r in data["RelicData"]["RelicTypes"]:
        by_faction = {
            faction_name(f["FractionId"]): f["SkillIds"]
            for f in r.get("SkillIdsByFaction") or []
            if f.get("SkillIds")
        }
        relics.append(
            {
                "id": r["Id"],
                "name": r["Name"],
                "rarity": r["Rarity"],
                "skills": r.get("SkillIds") or [],
                "by_faction": by_faction,
            }
        )
    levels = data["RelicData"].get("SkillLevelByRelicLevel") or {}
    skill_levels = {
        str(level): skill for level, skill in sorted(levels.items(), key=lambda kv: int(kv[0]))
    }
    stones = {
        str(s["Id"]): {"name": s["Name"], "skills": s.get("SkillIds") or []}
        for s in data["RelicData"].get("RelicStoneTypes") or []
    }
    return {
        "sets": sets,
        "relics": relics,
        "relic_skill_levels": skill_levels,
        "relic_stones": stones,
    }


def source_skill_ids(sources):
    return (
        {t["skill"] for s in sources["sets"] for t in s["skills"]}
        | {i for r in sources["relics"] for i in r["skills"]}
        | {i for r in sources["relics"] for ids in r["by_faction"].values() for i in ids}
    )
