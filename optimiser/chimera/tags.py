"""
tags.py - what a champion (or its gear) can bring to the Chimera fight (`Tag`): a status effect
kind it places, a skill effect, or a mechanic; what each of the Chimera's forms is immune to;
and what each is called in game.

- `Side`, `Mechanic`, `Tag`: what can be brought
- `BOSS_IMMUNE`, `FORM_ALLOWS`, `NEVER_LANDS`, `only_in`, `immune_to`: the Chimera's
  immunities, by form
- `EFFECT_LABELS`, `STATUS_LABELS`, `tag_label`, `plain_label`, `spaced`: their names
- `debuff`, `buff`, `SAME_KIND`, `status_kind`: making tags
"""

import re
from dataclasses import dataclass
from enum import StrEnum

# What every form of the Chimera is immune to (its Almighty passives: control debuffs), and
# what each form lets through all the same (Almighty Ram, Almighty Viper).
BOSS_IMMUNE = frozenset(
    {
        "Petrification",
        "Stun",
        "Freeze",
        "Sleep",
        "Provoke",
        "BlockActiveSkills",
        "BlockPassiveSkills",
        "Fear",
        "Enfeeble",
        "Ensnare",
        "Fatigue",
        "HuntersMark",
        "Nullifier",
    }
)

FORM_ALLOWS = {"Ram": frozenset({"Fear"}), "Snake": frozenset({"BlockActiveSkills"})}
# Debuffs no form takes: never worth bringing.
NEVER_LANDS = BOSS_IMMUNE - frozenset().union(*FORM_ALLOWS.values())

# Skill effects a team can be asked to bring (`Side.EFFECT` tags), by what the game calls
# them; the rest of a skill's effect kinds are machinery. Left out: what the Chimera is immune
# to (Turn Meter reduction, cooldown increases, MAX HP destruction, HP swaps).
EFFECT_LABELS = {
    "IncreaseBuffLifetime": "Extend buffs",
    "IncreaseDebuffLifetime": "Extend debuffs",
    "IncreaseStamina": "Fill Turn Meter",
    "ExtraTurn": "Extra turn",
    "ReduceCooldown": "Reduce cooldowns",
    "RemoveDebuff": "Remove debuffs (cleanse)",
    "ReduceDebuffLifetime": "Shorten debuffs on the team",
    "TransferDebuff": "Transfer debuffs",
    "Heal": "Heal",
    "Revive": "Revive",
    "RemoveBuff": "Remove buffs (strip)",
    "StealBuff": "Steal buffs",
    "ReduceBuffLifetime": "Shorten the Chimera's buffs",
    "MultiplyDebuff": "Spread debuffs",
    "Detonate": "Detonate debuffs",
    "TeamAttack": "Ally Attack",
    "PassiveCounterattack": "Counterattack (passive)",
    "PassiveBlockDebuff": "Block debuffs (passive)",
    "PassiveUnkillable": "Unkillable (passive)",
    "PassiveReflectDamage": "Reflect damage (passive)",
}

# What a status effect kind is called in game, where its name doesn't say.
STATUS_LABELS = {
    "Fear": "Fear / True Fear",
    "IncreaseDamageTaken": "Weaken",
    "Invisible": "Veil / Perfect Veil",
    "LifeDrainOnDamage": "Leech",
    "IncreasePoisoning": "Poison Sensitivity",
    "ContinuousDamage": "Poison",
    "Burn": "HP Burn",
    "FireMark": "Smite",
    "MirrorDamage": "Pain Link",
    "Negator": "Intercept",
    "SimpleStoneSkin": "Stone Skin",
    "BlockDebuff": "Block Debuffs",
    "BlockBuffs": "Block Buffs",
    "ReviveOnDeath": "Revive on Death",
    "DecreaseDefence": "Decrease DEF",
    "DecreaseAttack": "Decrease ATK",
    "DecreaseSpeed": "Decrease SPD",
    "DecreaseAccuracy": "Decrease ACC",
    "DecreaseResistance": "Decrease RES",
    "IncreaseDefence": "Increase DEF",
    "IncreaseAttack": "Increase ATK",
    "IncreaseSpeed": "Increase SPD",
    "IncreaseAccuracy": "Increase ACC",
    "IncreaseResistance": "Increase RES",
    "IncreaseCriticalChance": "Increase C.RATE",
    "IncreaseCriticalDamage": "Increase C.DMG",
}


class Side(StrEnum):
    DEBUFF = "debuff"  # on the Chimera
    BUFF = "buff"  # on the team
    EFFECT = "effect"  # a skill effect (`EFFECT_LABELS`)
    MECHANIC = "mechanic"


class Mechanic(StrEnum):
    TARGET_HP_DAMAGE = "damage based on enemy MAX HP"
    COUNTER_OR_ALLY_ATTACK = "counterattack or Ally Attack skill"
    PASSIVE_REFLECT = "passive Reflect Damage"
    REVIVE = "revive"
    PASSIVE_UNKILLABLE = "passive Unkillable"


@dataclass(frozen=True)
class Tag:
    """Something a champion can bring: a status effect kind it places (`DecreaseDefence`,
    both strengths), a skill effect (`EFFECT_LABELS`), or a mechanic (a `Mechanic` value).
    `key` names it in a URL."""

    side: Side
    name: str

    @property
    def key(self) -> str:
        return f"{self.side}:{self.name}"


def only_in(tag: Tag) -> tuple[str, ...]:
    """The forms a debuff the Chimera is otherwise immune to lands in (none: any form)."""
    if tag.side != Side.DEBUFF or tag.name not in BOSS_IMMUNE:
        return ()

    return tuple(form for form, allows in FORM_ALLOWS.items() if tag.name in allows)


def immune_to(form: str) -> frozenset[str]:
    return BOSS_IMMUNE - FORM_ALLOWS.get(form, frozenset())


def debuff(*kinds: str) -> frozenset[Tag]:
    return frozenset(Tag(Side.DEBUFF, kind) for kind in kinds)


def buff(*kinds: str) -> frozenset[Tag]:
    return frozenset(Tag(Side.BUFF, kind) for kind in kinds)


# Statuses that are another's kind under another name (a set's shield is a Shield).
SAME_KIND = {"ArtifactSet_Shield": "Shield"}


def status_kind(status: str) -> str:
    """A status effect's kind: its name without the strength (DecreaseDefence60, Fear2)."""
    return SAME_KIND.get(status) or re.sub(r"\d+p?$", "", status)


def tag_label(tag: Tag) -> str:
    """The tag in words, with where it lands ("Decrease DEF on the Chimera")."""
    if tag.side in (Side.MECHANIC, Side.EFFECT):
        return plain_label(tag)

    where = "on the Chimera" if tag.side == Side.DEBUFF else "on the team"
    return f"{STATUS_LABELS.get(tag.name, spaced(tag.name))} {where}"


def plain_label(tag: Tag) -> str:
    """The tag in words, alone ("Decrease DEF")."""
    match tag.side:
        case Side.MECHANIC:
            return tag.name
        case Side.EFFECT:
            return EFFECT_LABELS[tag.name]
        case _:
            return STATUS_LABELS.get(tag.name, spaced(tag.name))


def spaced(name: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
