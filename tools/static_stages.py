"""
static_stages.py - the game's stages: every area, region and stage, its enemies, their skills
and what they block, team restrictions, stat modifiers, the Chimera's trials and the clan
boss's timing (`enemies.json`), and the gear each dungeon stage drops (`loot.json`).

- `EFFECT_KIND_GROUPS`: effect kind groups as the game's code lists them (recheck after an update)
- `build_enemies`, `build_loot`: a file each
- `build_areas`, `build_condition`, `build_modifier`, `build_placement`, `slot_modifiers`,
  `build_enemy_skill`, `build_effect`, `build_blocks`, `build_trial`, `build_trial_rewards`,
  `build_raid_timing`, `stage_loot`: their steps
"""

import re

from tools.static_skills import TAGS

# The effect kinds in an effect kind group the static data names by number, as the game's code
# lists them (`EffectKindGroupExtensions..cctor`, its arrays' data in global-metadata.dat; read
# for 11.90.1). Only what a block names: 12, BossImmunitiesEffects, the control debuffs, damage
# over time, Decrease SPD, Heal Reduction and the instant effects bosses shrug off.
EFFECT_KIND_GROUPS = {
    12: (3004, 3001, 3003, 3002, 3015, 3019, 3006, 3017, 3025, 3027, 3028, 3032, 3033, 3034)
    + (5009, 15001, 5004, 4008, 5001, 5007, 3007, 3014, 3103, 3005),
}


def build_loot(stage_data, enums):
    """The gear each dungeon stage drops, by region and difficulty (stages in order): `pieces`
    a run gives on average (`Reward`: `Count` draws among its rewards by weight, an artifact's
    count its min–max), and their odds by rank and rarity (`ArtifactProbsByRankId`, `ByRarityId`,
    drawn apart). A region with one difficulty lists it as "None"; it's written "Normal", as
    events name it. For the events scoring gear by rank and rarity (`optimiser.loot`)."""
    stages = {stage["Id"]: stage for stage in stage_data["Stages"]}
    ranks, rarities = enums["ArtifactRankId"], enums["ItemRarity"]
    loot = {}

    for area in stage_data["Areas"]:
        for region in area.get("Regions") or []:
            for difficulty, ids in (region.get("StageIdsByDifficulty") or {}).items():
                drops = [stage_loot(stages[i].get("Reward") or {}, ranks, rarities) for i in ids]
                if any(drops):
                    named = "Normal" if difficulty == "None" else difficulty
                    loot.setdefault(region["Id"], {})[named] = drops

    return loot


def stage_loot(reward, ranks, rarities):
    """A stage's gear: pieces a run gives, and their odds by rank and rarity (None if none)."""
    by_rank = reward.get("ArtifactProbsByRankId") or {}
    by_rarity = reward.get("ArtifactProbsByRarityId") or {}
    rewards = reward.get("Rewards") or []
    weights = sum(r["Probability"] for r in rewards)

    if not (by_rank and by_rarity and weights):
        return None

    pieces = sum(
        r["Probability"] / weights * (r["MinCount"] + r["MaxCount"]) / 2
        for r in rewards
        if r["Type"] == "Artifact"
    )

    def shares(odds, names):
        total = sum(odds.values())
        return {names[str(key)]: value / total for key, value in odds.items()}

    return {
        "pieces": reward.get("Count", 1) * pieces,
        "ranks": shares(by_rank, ranks),
        "rarities": shares(by_rarity, rarities),
    }


GRADE_NAMES = {f"Stars{n}": n for n in range(1, 7)}


COMPLETED = re.compile(r"challengeCompletedById\((\d+)\)")


def build_enemies(data, skills, enums):
    """Every stage's enemy teams (types and base stats are in hero_types.json), the restrictions
    on the player's team, the stages' stat modifiers, which types are bosses, the enemies'
    skills (text and effects), the stages' battle quests (the stars: "Beat Stage", a
    challenge…, with their texts), and the boss modes' own tables: clan boss difficulties,
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
            "quests": [
                {"id": q["QuestId"], "parameter": q["Parameter"]}
                for q in stage.get("BattleQuests") or []
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
        "skills": {
            str(i): build_enemy_skill(skills[i], enums) for i in sorted(skill_ids) if i in skills
        },
        "shield_caps": data["GameplayData"].get("SpecificShieldCapByArea") or {},
        "quests": {
            str(q["Id"]): q["Description"] for q in data["BattleQuestData"]["BattleQuestTypes"]
        },
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


def build_enemy_skill(skill, enums):
    return {
        "name": skill["Name"],
        "group": skill["Group"],
        "cooldown": skill["Cooldown"],
        "description": TAGS.sub("", skill["Description"] or "").replace("\r\n", "\n"),
        "effects": [build_effect(e, enums) for e in skill["Effects"] or []],
    }


def build_effect(e, enums):
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
        "blocks": build_blocks(e.get("BlockEffectParams"), enums),
    }
    return {k: v for k, v in effect.items() if v is not None}


def build_blocks(params, enums):
    """What a block effect (`PassiveBlockEffect`) stops: effect kinds by name (its groups'
    members, `EFFECT_KIND_GROUPS`, and those it names, less those it excludes), status effect
    types by name, `all_but`: it stops everything but those; `unread_groups`: groups this
    doesn't know the members of."""
    if not params:
        return None

    groups = params.get("EffectKindGroups") or []
    kinds = {k for g in groups for k in EFFECT_KIND_GROUPS.get(g, ())}
    kinds |= set(params.get("EffectKindIds") or [])
    kinds -= set(params.get("ExcludeEffectKinds") or [])
    kind_names, status_names = enums["EffectKindId"], enums["StatusEffectTypeId"]
    blocks = {
        "kinds": sorted(kind_names.get(str(k), str(k)) for k in kinds),
        "statuses": sorted(
            status_names.get(str(t), str(t)) for t in params.get("EffectTypeIds") or []
        ),
        "all_but": bool(params.get("BlockAllExcludeSelected")),
        "unread_groups": [g for g in groups if g not in EFFECT_KIND_GROUPS],
    }
    return {k: v for k, v in blocks.items() if v}


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
