"""
kits.py - what a champion can bring to the fight (`Kit`): every tag its skills place or do, in
any of its forms, each rated (`Rating`) for how far it can be counted on: uptime (turns it
lasts against how often the skill comes round, with the champion's cooldown books) ×
reliability (its chance with chance books, less for a condition) × reach (the team, one ally,
the caster alone; debuffs in full). Effects the game never applies against a boss (Lamasu's
True Fear) don't count: the ratings are against a boss. A mythical's other form counts at
`OTHER_FORM`. A kit also says how many of each tag one skill places at most (`counts`: two
Poisons), for needs counting instances.

- `Rating`, `Kit`: a champion's kit
- `REACH_TEAM`, `REACH_ALLY`, `REACH_SELF`, `SELF`, `TEAM`, `CONDITIONAL`, `OTHER_FORM`,
  `ENEMY_EFFECTS`, `MECHANIC_KINDS`: the scoring's weights and rules
- `Cast`: how a champion casts a skill
- `kit_of`: a champion's kit
- `skill_ratings`, `cast_of`, `rate` (`describe`), `mechanic_rating`, `placement_tag`,
  `reach_of`, `skill_mechanics`: its steps
- `best_ratings`, `skill_counts`, `most_counts`: each tag's best rating, and the most of it one
  skill places, where several sources bring it
- `wantable`, `candidates`, `strength`: champions, and what they can be asked to bring
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property

from optimiser.account import Account, Champion
from optimiser.tables import Placement, Skill
from optimiser.teams.tags import EFFECT_LABELS, Mechanic, Side, Tag, status_kind, tag_label

# Scoring (`Rating`): how far each thing a champion brings can be counted on. Reach: a buff
# or an ally-side effect on the whole team counts in full, on one ally less, on the caster
# alone least (every debuff counts in full: there's one enemy to place it on). A condition
# gating an effect (on a crit, if the target has…) makes it less reliable; a mythical's other
# form's skills count at half, since it must switch to use them; gear meets a need this
# reliably.
REACH_TEAM, REACH_ALLY, REACH_SELF = 1.0, 0.5, 0.35

SELF = frozenset({"Producer", "Owner", "RelationProducer"})

TEAM = frozenset({"AllAllies"})

CONDITIONAL = 0.6

OTHER_FORM = 0.5

# Skill effects that land on the enemy, not the team (their reach is in full).
# Counterattacks and reflected damage count in full too: what matters is the enemy is hit.
ENEMY_EFFECTS = frozenset(
    {"RemoveBuff", "StealBuff", "ReduceBuffLifetime", "MultiplyDebuff", "Detonate"}
    | {"IncreaseDebuffLifetime", "PassiveCounterattack", "PassiveReflectDamage"}
)

# The skill effects behind each mechanic, whose placements rate it.
MECHANIC_KINDS = {
    Mechanic.TARGET_HP_DAMAGE: frozenset({"Damage"}),
    Mechanic.COUNTER_OR_ALLY_ATTACK: frozenset(
        {"TeamAttack", "PassiveCounterattack", "ActivateCounterattack"}
    ),
    Mechanic.PASSIVE_REFLECT: frozenset({"PassiveReflectDamage"}),
    Mechanic.REVIVE: frozenset({"Revive"}),
    Mechanic.PASSIVE_UNKILLABLE: frozenset({"PassiveUnkillable"}),
}


@dataclass(frozen=True)
class Rating:
    """How far a champion's source of a tag can be counted on, 0 to 1: `score` is uptime
    (turns it lasts against how often the skill comes round; how often, for an instant
    effect), reliability (its chance with the champion's books, less for a condition) and
    reach (team, one ally, self) multiplied. `detail` says how, in words."""

    score: float
    uptime: float
    reliability: float
    reach: float
    detail: str


@dataclass(frozen=True)
class Kit:
    """A champion, and what it can bring: the best `Rating` of each tag, and `counts`: how many
    of it one of its skills places at most (a tag missing places one)."""

    champion: Champion
    ratings: dict[Tag, Rating]
    counts: dict[Tag, float] = field(default_factory=dict)

    @cached_property
    def tags(self) -> frozenset[Tag]:
        return frozenset(self.ratings)


@dataclass(frozen=True)
class Cast:
    """How a champion casts a skill: every so many turns (cooldown less its cooldown books;
    passives and A1s every turn), with its chance books' bonus, and `switch`: `OTHER_FORM`
    for a mythical's other form, else 1."""

    every: int
    chance_bonus: float
    switch: float


def wantable(account: Account, never: frozenset[str]) -> list[Tag]:
    """What a team can be asked to bring besides: every debuff (but those in `never`: no
    target takes them), buff and skill effect any champion on the account brings, by label."""
    tags = {
        tag
        for champion in account.champions.values()
        for tag in kit_of(account, champion).tags
        if tag.side != Side.MECHANIC and not (tag.side == Side.DEBUFF and tag.name in never)
    }
    return sorted(tags, key=lambda t: (list(Side).index(t.side), tag_label(t, "the enemy")))


def candidates(account: Account, min_grade: int) -> list[Champion]:
    """Champions at `min_grade`★ or above, the best copy of each (ascensions together)."""
    best: dict[int, Champion] = {}

    for champion in account.champions.values():
        if champion.grade < min_grade:
            continue

        kind = champion.type_id // 10
        held = best.get(kind)
        if held is None or strength(champion) > strength(held):
            best[kind] = champion

    return sorted(best.values(), key=lambda c: c.name)


def kit_of(account: Account, champion: Champion) -> Kit:
    """What the champion's skills can bring, in any of its forms (mythicals have two), and
    how well (`Rating`, with its own skill books; the other form's at `OTHER_FORM`)."""
    forms = account.tables.hero_forms.get(champion.type_id, ())
    rated = []
    counted = []

    for index, form in enumerate(forms):
        switch = OTHER_FORM if len(forms) > 1 and index != champion.form else 1.0

        for skill_id in form.skills:
            if skill := account.tables.skills.get(skill_id):
                level = champion.skill_levels.get(skill_id, 1)
                rated += skill_ratings(skill, level, switch)
                counted.append(skill_counts(skill))

    return Kit(champion, best_ratings(rated), most_counts(counted))


def best_ratings(rated: Iterable[tuple[Tag, Rating]]) -> dict[Tag, Rating]:
    """Each tag's best rating."""
    best: dict[Tag, Rating] = {}

    for tag, rating in rated:
        if tag not in best or rating.score > best[tag].score:
            best[tag] = rating

    return best


def skill_counts(skill: Skill) -> dict[Tag, float]:
    """How many of each tag the skill places (each effect's `repeats`), those placing more
    than one."""
    counts: dict[Tag, float] = {}

    for placement in skill.placements:
        if (
            placement.on_boss is not False
            and not placement.echo
            and (tag := placement_tag(placement))
        ):
            counts[tag] = counts.get(tag, 0) + placement.repeats

    return {tag: placed for tag, placed in counts.items() if placed > 1}


def most_counts(counted: Iterable[dict[Tag, float]]) -> dict[Tag, float]:
    """The most of each tag any one of them places."""
    most: dict[Tag, float] = {}

    for counts in counted:
        for tag, placed in counts.items():
            most[tag] = max(most.get(tag, 1), placed)

    return most


def skill_ratings(skill: Skill, level: int, switch: float) -> list[tuple[Tag, Rating]]:
    """Each tag the skill brings, rated at the skill's level (its books)."""
    cast = cast_of(skill, level, switch)
    landing = [placement for placement in skill.placements if placement.on_boss is not False]
    rated = [
        (tag, rate(placement, tag, cast))
        for placement in landing
        if (tag := placement_tag(placement))
    ]
    mechanics = [
        (Tag(Side.MECHANIC, m), mechanic_rating(landing, m, cast))
        for m in skill_mechanics(skill, landing)
    ]
    return rated + mechanics


def cast_of(skill: Skill, level: int, switch: float) -> Cast:
    """How the skill is cast at its level: level L has its first L-1 books."""
    books = skill.books[: max(level - 1, 0)]
    chance_bonus = sum(b.value for b in books if b.type == "EffectChance")
    cooldown = max(skill.cooldown - sum(1 for b in books if b.type == "CooltimeTurn"), 0)
    every = 1 if skill.group == "Passive" else max(cooldown, 1)
    return Cast(every, chance_bonus, switch)


def mechanic_rating(placements: list[Placement], mechanic: Mechanic, cast: Cast) -> Rating:
    """A mechanic, rated as the best of the skill's effects (`placements`) behind it."""
    tag = Tag(Side.MECHANIC, mechanic)
    rated = [
        rate(placement, tag, cast)
        for placement in placements
        if placement.kind in MECHANIC_KINDS[mechanic]
    ]
    fallback = Rating(cast.switch, 1.0, 1.0, 1.0, "its skills")
    return max(rated, key=lambda r: r.score, default=fallback)


def placement_tag(placement: Placement) -> Tag | None:
    match placement.kind:
        case "ApplyDebuff" if placement.status and placement.target not in SELF:
            return Tag(Side.DEBUFF, status_kind(placement.status))
        case "ApplyBuff" if placement.status:
            return Tag(Side.BUFF, status_kind(placement.status))
        case kind if kind in EFFECT_LABELS:
            return Tag(Side.EFFECT, kind)

    return None


def rate(placement: Placement, tag: Tag, cast: Cast) -> Rating:
    """Uptime × reliability × reach (× `cast.switch`)."""
    base = 1.0 if placement.chance is None else placement.chance
    chance = 1.0 if base >= 1 else min(1.0, base + cast.chance_bonus)
    reliability = chance * (CONDITIONAL if placement.on_boss is None else 1.0)

    turns = placement.turns
    if turns is not None and turns < 0:  # lasts the fight
        uptime = 1.0
    elif turns:
        uptime = min(1.0, turns / cast.every)
    else:
        uptime = 1.0 / cast.every

    reach = reach_of(placement, tag)
    score = uptime * reliability * reach * cast.switch
    return Rating(score, uptime, reliability, reach, describe(placement, cast, chance, reach))


def describe(placement: Placement, cast: Cast, chance: float, reach: float) -> str:
    """A rating in words: "2 turns, every 3 turns, 75% chance, one ally"."""
    turns = placement.turns
    lasts = f"{turns} turn{'s' if turns != 1 else ''}" if turns and turns > 0 else ""
    parts = [
        lasts or ("instant" if turns is None else ""),
        "every turn" if cast.every == 1 else f"every {cast.every} turns",
        f"{chance:.0%} chance" if chance < 1 else "",
        "conditional" if placement.on_boss is None else "",
        "other form" if cast.switch < 1 else "",
        "can't be resisted" if placement.unresistable else "",
    ]

    if reach < 1:
        parts.append("self only" if reach == REACH_SELF else "one ally")

    return ", ".join(part for part in parts if part)


def reach_of(placement: Placement, tag: Tag) -> float:
    """Debuffs, mechanics (what matters is the enemy is hit) and effects on the enemy reach
    in full; buffs and effects on the team by who they land on."""
    if tag.side in (Side.DEBUFF, Side.MECHANIC):
        return REACH_TEAM

    if tag.side == Side.EFFECT and tag.name in ENEMY_EFFECTS:
        return REACH_TEAM

    if placement.target in TEAM:
        return REACH_TEAM

    return REACH_SELF if placement.target in SELF else REACH_ALLY


def skill_mechanics(skill: Skill, placements: list[Placement]) -> set[Mechanic]:
    """The mechanics the skill has: its effects' (`placements`, `MECHANIC_KINDS`), and damage
    based on the target's HP from its formulas (any damage skill has a Damage effect)."""
    kinds_placed = {placement.kind for placement in placements}
    found = {
        mechanic
        for mechanic, kinds in MECHANIC_KINDS.items()
        if mechanic != Mechanic.TARGET_HP_DAMAGE and kinds_placed & kinds
    }

    if skill.target_hp_damage:
        found.add(Mechanic.TARGET_HP_DAMAGE)

    return found


def strength(champion: Champion) -> float:
    """Under 1: rank first, then awakening, then level."""
    return (champion.grade * 1000 + champion.awakening * 100 + champion.level) / 7000
