"""
static_skills.py - every skill a champion, set or relic has, as `skills.json`: what it places
and on whom, how it scales, and whether it reaches a boss at all, read three-valued from its
conditions against what's true of a boss (`on_boss`, `BOSS_FACTS`).

- `TAGS`: the markup the game's texts carry (also stripped from enemy skills' texts)
- `build_skills`: the file
- `skill_kit`, `condition_facts`, `on_boss`, `eval_condition`, `and3`, `or3`: its steps
"""

import re

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


def build_skills(skills, heroes, status_names, extra_ids=()):
    """The champions' skills: name, the game's text (markup stripped), whether it's AoE, its
    unconditional damage hits (formula, count, the skill's own DEF modifier), the damage bonus
    each book adds, and the formulas of its other effects that scale with the caster's stats
    (`scaling`: kind and formula).
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
            "description": TAGS.sub("", skill["Description"] or "").replace("\r\n", "\n"),
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
    against a boss: `on_boss`, whether it can be resisted, `repeats`: how many it places, the
    effect's count times its stack count; a relic's: `relic_level`, the relic skill level it's
    for; `echo`: the status whose placing it answers by placing another), and its `books` in
    order (type and value: the chance, cooldown and the rest each adds)."""
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
            "repeats": (effect.get("Count") or 1) * (effect.get("StackCount") or 1),
            **condition_facts(effect.get("Condition") or ""),
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


def condition_facts(condition):
    """What an effect's condition says about it beyond `on_boss`: the relic skill level it's
    for, and the status it echoes (placed again when one is placed)."""
    facts = {}
    if level := RELIC_LEVEL.search(condition):
        facts["relic_level"] = int(level.group(1))
    if echo := ECHOED.search(condition):
        facts["echo"] = echo.group(1)
    return facts


TAGS = re.compile(r"<[^>]+>")


RELIC_LEVEL = re.compile(r"relicSkillLevel==(\d+)")


ECHOED = re.compile(r"StatusEffectWithTypeIdIsApplied\((\w+)\)")


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
