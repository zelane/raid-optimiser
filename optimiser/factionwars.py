"""
factionwars.py - Faction Wars as a team finder's base needs: each crypt (a faction's, only its
champions admitted) and its stages by difficulty, and a stage's challenge (its last battle
quest, the third star) as needs (`challenge_needs`, read from the quest's text). Bringing it
is what counts, not how much: "Place 10+ Stun debuffs" asks for a Stun, scored on how far the
team can count on it. Quests about how the fight goes (turns, losses, weak hits, damage) or
the team's make-up aren't checked.

- `DIFFICULTIES`, `ENEMIES`, `QUEST_NEEDS`, `PLACED`: what's read (`PLACED`:
  a "Place N+ … debuffs" quest's debuff)
- `Crypt`, `Challenge`: the crypts, and a stage's challenge
- `effects`, `COUNTER`: tags the table builds on
- `crypts`, `challenge`, `challenge_needs`, `admits`: the entry points
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from optimiser.account import Champion, faction_name
from optimiser.enemies import CRYPT, FACTION_WARS, Enemies, Stage
from optimiser.teams.needs import AnyOf, Distinct, Need
from optimiser.teams.tags import Mechanic, Side, Tag, Target, buff, debuff

DIFFICULTIES = ("Normal", "Hard")

# What a challenge's needs are met against: the stage's enemies, waves and boss alike.
ENEMIES = Target("the enemies")


def effects(*kinds: str) -> frozenset[Tag]:
    return frozenset(Tag(Side.EFFECT, kind) for kind in kinds)


# The debuffs "Place N+ … debuffs" quests name, by the quest's word for them.
PLACED = {
    "Stun": "Stun",
    "Provoke": "Provoke",
    "Freeze": "Freeze",
    "Sleep": "Sleep",
    "Poison": "ContinuousDamage",
    "HP Burn": "Burn",
    "Block Revive": "BlockRevive",
    "Decrease SPD": "DecreaseSpeed",
}

COUNTER = frozenset({Tag(Side.MECHANIC, Mechanic.COUNTER_OR_ALLY_ATTACK)}) | buff("Counterattack")

# A challenge's text (its quest, parameter filled in) and what it needs: the first pattern
# matching it decides. Turn meter and cooldowns count only what a team does for itself (Fill
# Turn Meter, Reduce cooldowns): the effects on enemies aren't tags.
QUEST_NEEDS: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], tuple[Need, ...]]], ...] = (
    (
        re.compile(r"Place \d+\+ (.+?) debuffs"),
        lambda m: (AnyOf(debuff(PLACED[m.group(1)])),) if m.group(1) in PLACED else (),
    ),
    (re.compile(r"Place \d+\+ Taunt buffs"), lambda m: (AnyOf(buff("Taunt")),)),
    (re.compile(r"under Leech debuffs"), lambda m: (AnyOf(debuff("LifeDrainOnDamage")),)),
    (re.compile(r"under Hex debuffs"), lambda m: (AnyOf(debuff("Mark")),)),
    (re.compile(r"under Fear/True Fear debuffs"), lambda m: (AnyOf(debuff("Fear")),)),
    (re.compile(r"using Bomb debuffs"), lambda m: (AnyOf(debuff("TimeBomb")),)),
    (re.compile(r"under Perfect Veil"), lambda m: (AnyOf(buff("Invisible")),)),
    (
        re.compile(r"under (\d+) or more debuffs"),
        lambda m: (Distinct(Side.DEBUFF, int(m.group(1)), instances=True),),
    ),
    (re.compile(r"under (\d+) or more buffs"), lambda m: (Distinct(Side.BUFF, int(m.group(1))),)),
    (re.compile(r"Get an Extra Turn"), lambda m: (AnyOf(effects("ExtraTurn")),)),
    (re.compile(r"Manipulate Turn Meters"), lambda m: (AnyOf(effects("IncreaseStamina")),)),
    (re.compile(r"Manipulate skill cooldowns"), lambda m: (AnyOf(effects("ReduceCooldown")),)),
    (
        re.compile(r"Manipulate buff or debuff duration"),
        lambda m: (
            AnyOf(
                effects(
                    "IncreaseBuffLifetime",
                    "IncreaseDebuffLifetime",
                    "ReduceDebuffLifetime",
                    "ReduceBuffLifetime",
                )
            ),
        ),
    ),
    (re.compile(r"Heal your Champions"), lambda m: (AnyOf(effects("Heal")),)),
    (re.compile(r"Ally Attack skills or counterattacks"), lambda m: (AnyOf(COUNTER),)),
)


@dataclass(frozen=True)
class Crypt:
    """A faction's crypt: `region` (the game's id), its name, the faction it admits (display
    name), and its stages by difficulty, first to last."""

    region: str
    name: str
    faction: str
    stages: dict[str, tuple[int, ...]]


@dataclass(frozen=True)
class Challenge:
    """A stage's challenge: its text, and what it needs (`checked`: its text is read; else it's
    about the fight or the team's make-up, and nothing is asked)."""

    text: str
    needs: tuple[Need, ...]
    checked: bool


def crypts(enemies: Enemies) -> tuple[Crypt, ...]:
    """The crypts, in the game's order."""
    area = next(area for area in enemies.areas if area.id == FACTION_WARS)
    return tuple(
        Crypt(
            region.id,
            region.name,
            faction_name(region.id.removeprefix(CRYPT)),
            {d: region.stages[d] for d in DIFFICULTIES if d in region.stages},
        )
        for region in area.regions
    )


def challenge(stage: Stage) -> Challenge | None:
    """The stage's challenge: its last battle quest (the first two are "Beat Stage" and
    "5 Champions, no losses"), if it has one."""
    if len(stage.quests) < 3:
        return None

    text = stage.quests[-1].text
    needs = challenge_needs(text)
    return Challenge(text, needs or (), needs is not None)


def challenge_needs(text: str) -> tuple[Need, ...] | None:
    """What the challenge needs (`QUEST_NEEDS`), or None: nothing reads it."""
    for pattern, needs in QUEST_NEEDS:
        if match := pattern.search(text):
            return needs(match) or None

    return None


def admits(crypt: Crypt, champion: Champion) -> bool:
    return faction_name(champion.faction) == crypt.faction
