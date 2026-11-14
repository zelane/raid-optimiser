"""Turn the game's cached static data into named, typed JSON using a dump-derived schema.

    uv run python -m tools.static_export <static-data dir or file> schema/schema.json out/ [--full]

The cache (`LocalLow/Plarium/Raid_ Shadow Legends/static-data`) is decoded by
`tools.static_decode`; given the directory, its newest file is read.

Writes out/{sets,hero_types,bonuses,skills,glyphs,gear,enemies,effect_sources}.json (and
out/static.json with --full).
Exits non-zero if validation fails, which usually means the schema came from a dump
older than the game version: run `just schema-refresh`.
"""

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

import click

from optimiser.account import faction_name
from tools.static_decode import decode, newest

FIXED_ONE = 2**32  # SharedModel Fixed is 32.32 fixed point
PRIMITIVES = {
    "int",
    "uint",
    "long",
    "ulong",
    "short",
    "ushort",
    "byte",
    "sbyte",
    "double",
    "float",
    "bool",
    "string",
    "decimal",
    "Int32",
    "Int64",
}
LIST_RE = re.compile(
    r"^(?:List|IReadOnlyList|IList|IEnumerable|HashSet|IReadOnlyCollection|ICollection)<(.+)>$"
)


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
        self.unknown_keys = Counter()  # (class, key) present in data, absent from schema
        self.enum_misses = Counter()  # (enum, value) not in schema
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
        if t.startswith(
            ("Dictionary<", "IReadOnlyDictionary<", "SortedDictionary<")
        ) and isinstance(v, dict):
            kt, vt = split_args(t[t.index("<") + 1 : -1])
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
            }
        )
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


def build_gear(art):
    """Gear stats by level: `primary` (main stat at levels 0..max_level, by rank) and
    `ascension` (the ascension bonus at ascension levels 1..rank, ranks 4-6), each per stat
    and the slots it applies to. Rarity doesn't change either."""

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
    }


ENEMY_TARGETS = {
    "Target",
    "AllEnemies",
    "Boss",
    "EnemyWithHighestStamina",
    "MostInjuredEnemy",
    "RandomEnemy",
    "RandomEnemyWithMaxBuffsCount",
}


# Effects other than damage whose size scales with the caster's stats: what heals, shields,
# revives and bombs scale off.
SCALING_KINDS = {"Heal", "ApplyBuff", "Revive", "ApplyDebuff"}
OWN_STATS = re.compile(r"(?<![A-Z_])(ATK|DEF|HP|ACC|RES|SPD)(?![A-Z_])")


# Who a status effect lands on: debuffs on these targets are the caster's own (or its team's).
SELF_TARGETS = {"Producer", "Owner", "AllAllies", "RelationProducer"}
TARGET_HP = re.compile(r"TRG_(?:B_|M_|CUR_)?HP(?!_PERC)\b")


def build_effect_sources(data):
    """What else can bring buffs, debuffs and effects to a team: each artifact set's set
    skills (the pieces they take), and each relic type's skills, with those only a champion of
    one faction gets (by the factions' display names, `faction_name`). The skills are in
    skills.json."""
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
    return {"sets": sets, "relics": relics}


def source_skill_ids(sources):
    return (
        {t["skill"] for s in sources["sets"] for t in s["skills"]}
        | {i for r in sources["relics"] for i in r["skills"]}
        | {i for r in sources["relics"] for ids in r["by_faction"].values() for i in ids}
    )


def build_skills(skills, heroes, status_names, extra_ids=()):
    """The champions' skills: name, whether it's AoE, its unconditional damage hits (formula,
    count, the skill's own DEF modifier), the damage bonus each book adds, and the formulas of
    its other effects that scale with the caster's stats (`scaling`: kind and formula).
    Also what it can place and do, whatever the condition or chance: `debuffs` on enemies and
    `buffs` on its team (status effect names), every effect kind it has (`effect_kinds`:
    Revive, TeamAttack, PassiveCounterattack, …) and whether it hits for a share of the
    target's HP (`target_hp_damage`)."""
    wanted = {skill_id for h in heroes for f in h["forms"] for skill_id in f["skills"]}
    wanted |= set(extra_ids)
    out = {}
    for skill_id in sorted(wanted):
        skill = skills.get(skill_id)
        if not skill:
            continue
        hits = [
            e
            for e in skill["Effects"] or []
            if e["KindId"] == "Damage"
            and not e.get("Condition")
            and (e.get("TargetParams") or {}).get("TargetType") in ENEMY_TARGETS
        ]
        out[str(skill_id)] = {
            "name": skill["Name"],
            "group": skill["Group"],
            "cooldown": skill["Cooldown"],
            "aoe": any(e["TargetParams"]["TargetType"] == "AllEnemies" for e in hits),
            "hits": [
                {
                    "formula": e["MultiplierFormula"],
                    "count": e["Count"],
                    "defence_modifier": round(
                        (e.get("DamageParams") or {}).get("DefenceModifier") or 0, 6
                    ),
                }
                for e in hits
            ],
            # One entry per book, in order (level L has the first L-1); 0 for non-damage books.
            "book_damage": [
                round(b["Value"], 6) if b["SkillBonusType"] == "Attack" else 0
                for b in skill.get("SkillLevelBonuses") or []
            ],
            "scaling": [
                {"kind": e["KindId"], "formula": e["MultiplierFormula"]}
                for e in skill["Effects"] or []
                if e["KindId"] in SCALING_KINDS
                and OWN_STATS.search(e.get("MultiplierFormula") or "")
            ],
            **skill_kit(skill, status_names),
        }
    return out


def skill_kit(skill, status_names):
    """What the skill places and does (`debuffs`, `buffs`, `effect_kinds`), and how: each
    effect's `placements` (status or effect kind, chance, turns, target, whether it happens
    against a boss: `on_boss`, whether it can be resisted), and its `books` in order (type
    and value: the chance, cooldown and the rest each adds)."""
    debuffs, buffs, placements = set(), set(), []
    for effect in skill["Effects"] or []:
        statuses = (effect.get("ApplyStatusEffectParams") or {}).get("StatusEffectInfos") or []
        names = {status_names.get(str(s["TypeId"]), str(s["TypeId"])) for s in statuses}
        target = (effect.get("TargetParams") or {}).get("TargetType")
        target_condition = (effect.get("TargetParams") or {}).get("Condition")
        common = {
            "chance": effect.get("Chance"),
            "target": target,
            "on_boss": on_boss(effect.get("Condition"), target_condition),
        }
        if effect["KindId"] == "ApplyDebuff" and target not in SELF_TARGETS:
            debuffs |= names
        elif effect["KindId"] == "ApplyBuff":
            buffs |= names
        for s in statuses:
            placements.append(
                {
                    "kind": effect["KindId"],
                    "status": status_names.get(str(s["TypeId"]), str(s["TypeId"])),
                    "turns": s.get("Duration"),
                    "unresistable": s.get("ApplyMode") in ("Unresistable", "Guaranteed"),
                    **common,
                }
            )
        if not statuses:
            placements.append(
                {
                    "kind": effect["KindId"],
                    "status": None,
                    "turns": None,
                    "unresistable": False,
                    **common,
                }
            )
    return {
        "debuffs": sorted(debuffs),
        "buffs": sorted(buffs),
        "placements": placements,
        "books": [
            {"type": b["SkillBonusType"], "value": round(b["Value"], 6)}
            for b in skill.get("SkillLevelBonuses") or []
        ],
        "effect_kinds": sorted({e["KindId"] for e in skill["Effects"] or []}),
        "target_hp_damage": any(
            e["KindId"] == "Damage" and TARGET_HP.search(e.get("MultiplierFormula") or "")
            for e in skill["Effects"] or []
        ),
    }


GRADE_NAMES = {f"Stars{n}": n for n in range(1, 7)}
TAGS = re.compile(r"<[^>]+>")
COMPLETED = re.compile(r"challengeCompletedById\((\d+)\)")


# Condition atoms that hold in a fight against a lone boss (the Chimera, clan boss, ...).
BOSS_FACTS = {
    "targetIsBoss",
    "relationTargetIsBoss",
    "thereIsBossInCurrentRound",
    "ThereIsBossInTeam(enemyTeamId)",
}
CONDITION_TOKEN = re.compile(r"\s*(&&|\|\||!(?!=)|\(|\)|[^&|!()]+(?:\([^()]*\))?(?:!=[^&|()]+)?)")


def on_boss(*conditions):
    """Whether an effect gated by these conditions (the effect's own and its target's) happens
    against a lone boss: True always, False never ("!targetIsBoss"), None when it depends on
    something else (or a condition can't be read). Three-valued, `BOSS_FACTS` true, other atoms
    unknown."""
    result = True
    for condition in conditions:
        if condition:
            result = and3(result, eval_condition(condition))
    return result


def eval_condition(condition):
    tokens = [t.strip() for t in CONDITION_TOKEN.findall(condition)]
    if "".join(tokens) != re.sub(r"\s", "", condition):
        return None
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def either():
        value = both()
        while peek() == "||":
            take()
            value = or3(value, both())
        return value

    def both():
        value = unary()
        while peek() == "&&":
            take()
            value = and3(value, unary())
        return value

    def unary():
        token = take()
        if token == "!":
            value = unary()
            return None if value is None else not value
        if token == "(":
            value = either()
            if take() != ")":
                raise ValueError(condition)
            return value
        if token in ("&&", "||", ")"):
            raise ValueError(condition)
        return True if token in BOSS_FACTS else None

    try:
        value = either()
    except (IndexError, ValueError):
        return None
    return value if pos == len(tokens) else None


def and3(a, b):
    if a is False or b is False:
        return False
    return None if a is None or b is None else True


def or3(a, b):
    if a is True or b is True:
        return True
    return None if a is None or b is None else False


def build_enemies(data, skills):
    """Every stage's enemy teams (types and base stats are in hero_types.json), the restrictions
    on the player's team, the stages' stat modifiers, which types are bosses, the enemies'
    skills (text and effects), and the boss modes' own tables: clan boss difficulties,
    the Chimera's form sequence and trials, and per-area shield caps."""
    areas, stage_places = build_areas(data["StageData"]["Areas"])
    stages = {}
    for stage in data["StageData"]["Stages"]:
        area, region, difficulty = stage_places.get(stage["Id"], (None, None, None))
        stages[str(stage["Id"])] = {
            "area": area,
            "region": region,
            "difficulty": difficulty,
            "scene": stage["SceneName"],
            "team_size": stage["UserHeroesCount"],
            "conditions": [
                build_condition(c)
                for c in (stage.get("StartCondition") or {}).get("HeroConditions") or []
            ],
            "modifiers": [build_modifier(m) for m in stage.get("Modifiers") or []],
            "formations": [
                [build_placement(p) for p in f["HeroSlotsSetup"] or []]
                for f in stage.get("Formations") or []
            ],
        }
    enemy_types = {p["type"] for s in stages.values() for f in s["formations"] for p in f}
    heroes = {h["Id"]: h for h in data["HeroData"]["HeroTypes"]}
    bosses = {
        str(t): {
            "kind": heroes[t]["BossData"]["Type"],
            "unkillable": bool(heroes[t]["BossData"].get("IsUnkillable")),
        }
        for t in sorted(enemy_types)
        if t in heroes and heroes[t].get("BossData")
    }
    skill_ids = {
        s
        for t in enemy_types
        if t in heroes
        for f in heroes[t].get("Forms") or []
        for s in f.get("SkillTypeIds") or []
    }
    alliance = data["AllianceData"]
    chimera_tiers = alliance["ChimeraTypes"]
    trial_ids = {c["SkillTypeId"] for tier in chimera_tiers for c in tier["Challenges"]}
    return {
        "areas": areas,
        "stages": stages,
        "bosses": bosses,
        "skills": {str(i): build_enemy_skill(skills[i]) for i in sorted(skill_ids) if i in skills},
        "shield_caps": data["GameplayData"].get("SpecificShieldCapByArea") or {},
        "clan_boss": [
            {
                "difficulty": b["Id"],
                "health": b["Health"],
                "type": b["HeroTypeId"],
                "level": b["Level"],
                "stages": b["StageIdByElement"],
            }
            for b in alliance["BossTypes"]
        ],
        "chimera": {
            "forms": {k: v for k, v in alliance["ChimeraSequenceForms"].items()},
            "turns_between_forms": alliance["ChimeraTurnsCountBetweenForm"],
            "timing": build_raid_timing(alliance["Settings"]["AllianceChimeraSettings"]),
            "tiers": [
                {
                    "difficulty": t["DifficultyId"],
                    "health": t["Health"],
                    "stages": t["StageIds"],
                    "trials": [
                        build_trial(c, skills.get(c["SkillTypeId"]), trial_ids)
                        for c in t["Challenges"]
                    ],
                    "rewards": [build_trial_rewards(r) for r in t["ChimeraChallengeRewards"]],
                }
                for t in chimera_tiers
            ],
        },
    }


def build_raid_timing(settings):
    """What the prize offset's rule needs (`ChimeraExtensions.GetPrizeOffset`)."""
    return {
        "hours_between_raids": settings["HoursBetweenRaids"],
        "activity_hours": settings["RaidActivityHours"],
        "max_prize_offset": settings["MaxChimeraPrizeOffset"],
    }


def build_trial_rewards(raw):
    """One of a tier's reward lists, in the game's order: the prize offset shifts which trial
    gets which (`optimiser.chimera.rotation`)."""
    return {
        "form": raw["Form"],
        "part": raw["Part"],
        "by_level": {
            level: [
                {
                    "item": r.get("ResourceTypeId") or r.get("BlackMarketItemId") or r["Type"],
                    "count": r["MinCount"],
                }
                for r in reward["Rewards"] or []
            ]
            for level, reward in raw["RewardsByChallengeDifficulty"].items()
        },
    }


def build_areas(raw_areas):
    """The areas and their regions' stages by difficulty, and each stage's (area, region,
    difficulty)."""
    places, areas = {}, []
    for area in raw_areas:
        regions = []
        for region in area.get("Regions") or []:
            by_difficulty = region.get("StageIdsByDifficulty") or {}
            for difficulty, ids in by_difficulty.items():
                for stage_id in ids:
                    places[stage_id] = (area["Id"], region["Id"], difficulty)
            regions.append({"id": region["Id"], "name": region["Name"], "stages": by_difficulty})
        areas.append(
            {
                "id": area["Id"],
                "name": area["Name"],
                "user_level": (area.get("Condition") or {}).get("UserLevelRequired"),
                "regions": regions,
            }
        )
    return areas, places


def build_condition(c):
    """Which champions a stage admits: every one must match (counts are the team size)."""

    def listed(one, many):
        return many or ([one] if one else None)

    return {
        "min": c["MinCount"],
        "max": c["MaxCount"],
        "factions": listed(c["Fraction"], c["Fractions"]),
        "roles": listed(c["Role"], c["Roles"]),
        "rarities": listed(c["Rarity"], c["Rarities"]),
        "affinities": listed(c["Element"], c["Elements"]),
        "grade": c["Grade"],
        "race": c["Race"],
        "required_type": c["RequiredHeroTypeId"],
    }


def build_modifier(m):
    return {
        "wave": m["Round"],
        "stat": m["KindId"],
        "value": round(m["Value"], 6),
        "absolute": m["IsAbsolute"],
        "boss_only": bool(m["BossOnly"]),
    }


def build_placement(p):
    return {
        "wave": p["Round"],
        "slot": p["Slot"],
        "type": p["HeroTypeId"],
        "grade": GRADE_NAMES[p["Grade"]],
        "level": p["Level"],
        "boss": bool(p["IsHeroBoss"] or p["IsMainBoss"]),
        "modifiers": slot_modifiers(p.get("Modifiers") or {}, p["Round"]),
    }


def slot_modifiers(m, wave):
    """A slot's own modifiers (stat maps of percent and flat bonuses), as stage modifiers."""
    return [
        {
            "wave": wave,
            "stat": stat,
            "value": round(value, 6),
            "absolute": absolute,
            "boss_only": False,
        }
        for key, absolute in (("PercentBonus", False), ("FlatBonus", True))
        for stat, value in (m.get(key) or {}).items()
        if value
    ]


def build_enemy_skill(skill):
    return {
        "name": skill["Name"],
        "group": skill["Group"],
        "cooldown": skill["Cooldown"],
        "description": TAGS.sub("", skill["Description"] or "").replace("\r\n", "\n"),
        "effects": [build_effect(e) for e in skill["Effects"] or []],
    }


def build_effect(e):
    statuses = (e.get("ApplyStatusEffectParams") or {}).get("StatusEffectInfos") or []
    effect = {
        "kind": e["KindId"],
        "target": (e.get("TargetParams") or {}).get("TargetType"),
        "count": e["Count"],
        "chance": e.get("Chance"),
        "formula": e.get("MultiplierFormula"),
        "condition": e.get("Condition"),
        "statuses": [{"type": s["TypeId"], "turns": s["Duration"]} for s in statuses] or None,
        "defence_modifier": (e.get("DamageParams") or {}).get("DefenceModifier") or None,
        "fixed": (e.get("DamageParams") or {}).get("IsFixed") or None,
    }
    return {k: v for k, v in effect.items() if v is not None}


def build_trial(challenge, skill, trial_ids):
    """A Chimera trial: its part and level, what it asks, and its target from the trial's
    hidden skill (damage or a count; `counter_limit`: the counter it must finish within, the
    Chimera's turns by the text, off by one from it; `requires`: the trial done first;
    `rules`: the conditions of its hidden skill's effects, which say what counts)."""
    start = next(
        (e for e in (skill or {}).get("Effects") or [] if e["KindId"] == "StartChallenge"), {}
    )
    params = start.get("ChallengeParams") or {}
    requires = [
        int(i) for i in COMPLETED.findall(start.get("Condition") or "") if int(i) in trial_ids
    ]
    return {
        "skill": challenge["SkillTypeId"],
        "form": challenge["Form"],
        "part": challenge["Part"],
        "level": challenge["Difficulty"],
        "statuses": challenge["Effects"],
        "description": TAGS.sub("", challenge["Description"] or ""),
        "target": params.get("TargetProgress"),
        "counter_limit": params.get("CounterLimit"),
        "damage": bool(params.get("BasedOnDamage")),
        "requires": requires[0] if requires else None,
        "rules": [e["Condition"] for e in (skill or {}).get("Effects") or [] if e.get("Condition")],
    }


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
    enemies = build_enemies(data, skills)
    json.dump(enemies, open(out / "enemies.json", "w"), ensure_ascii=False)
    if full:
        json.dump(data, open(out / "static.json", "w"), ensure_ascii=False)

    print(f"{len(sets)} sets, {len(heroes)} hero types -> {out.resolve()}")
    if conv.unknown_keys:
        top = ", ".join(f"{c}.{k}" for (c, k), _ in conv.unknown_keys.most_common(8))
        print(f"note: {len(conv.unknown_keys)} keys not in schema (kept as '?key'), e.g. {top}")
        print("      (the dump predates this game version: just schema-refresh)")
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
