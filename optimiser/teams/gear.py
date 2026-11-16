"""
gear.py - what a team can wear or is assumed to have beyond its skills (`Loadout`): artifact
sets and owned relics any champion can wear (`Gear`, from `effect_sources.json`; a relic's
faction skills only for a champion of that faction), and what the user assumes. Gear any
champion can wear meets needs for any team (`Given`); faction skills and single champions'
assumptions join those champions' kits (`equip`). For a count of debuff instances, gear any
champion can wear that places a Poison (the Toxic set) is one Poison more any team brings.

A relic's skills come in tiers, one per relic skill level (its level reaches them:
`RelicSource.skill_level`); only the tier the relic is at counts (for gear any champion can
wear, the best copy the account has). A relic one champion wears (a team slot's: `worn_relic`)
joins that champion's kit (`wear`), and an effect echoing a status (Sporeburst Rod: a placed
Poison may place another) makes the champion's own count of it go up by its chance (`echoes`).

- `Gear`, `Assumed`, `Loadout`, `DEFAULT_GEAR`, `ASSUMED`: what a team can wear or is
  assumed to have
- `GearSource`, `SetSource`, `RelicSource`, `load_effect_sources`, `gear_options`
  (`relic_sources`, `gear_of`, `best_level`), `assumed_gear`, `worn_relic`: where gear
  comes from
- `at_level`, `echoes_of`: a relic's skills at its level
- `with_gear` (`geared`), `equip`, `wear`: what it changes
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

from optimiser.account import (
    Account,
    Champion,
    Relic,
    Skill,
    faction_label,
    faction_name,
    read_json,
)
from optimiser.teams.kits import Kit, Rating, best_ratings, most_counts, skill_counts, skill_ratings
from optimiser.teams.needs import AnyOf, Distinct, Given, Need, stacking_tags
from optimiser.teams.tags import Side, Tag, plain_label, status_kind


@dataclass(frozen=True)
class Gear:
    """Something a champion can wear that brings buffs, debuffs or effects: an artifact set's
    skills, a relic's (`faction`: skills only a champion of that faction gets), or something
    the user assumes a team has. `ratings`: how far each can be counted on; `counts`: how many
    of it one skill places at most (`Kit.counts`). `key` names it in a URL ("set:DotRate",
    "relic:91:Demonspawn", "assumed:buff:Shield")."""

    key: str
    name: str
    kind: str  # set, relic, assumed
    faction: str | None
    ratings: dict[Tag, Rating]
    counts: dict[Tag, float] = field(default_factory=dict)
    echoes: dict[Tag, float] = field(default_factory=dict)  # tag -> chance it's placed again

    @property
    def tags(self) -> frozenset[Tag]:
        return frozenset(self.ratings)


@dataclass(frozen=True)
class Assumed:
    """Something the user says a champion brings (its kit gets it, in full), whatever the
    data says: a blessing, a book to come."""

    tag: Tag
    champion: Champion

    @property
    def key(self) -> str:
        return f"{self.champion.id}@{self.tag.key}"


@dataclass(frozen=True)
class Loadout:
    """What the team can wear and is assumed to have, beyond its skills: gear any champion
    (of its faction) can wear, and what given champions are assumed to bring."""

    gear: tuple[Gear, ...] = ()
    assumed: tuple[Assumed, ...] = ()

    @property
    def team_gear(self) -> tuple[Gear, ...]:
        """Gear any champion can wear: what it brings, any team has."""
        return tuple(g for g in self.gear if g.faction is None)


# The Toxic set: any champion can wear one; on unless the user says otherwise.
DEFAULT_GEAR = ("set:DotRate",)
# What's assumed counts in full.
ASSUMED = Rating(1.0, 1.0, 1.0, 1.0, "assumed")


def with_gear(needs: tuple[Need, ...], gear: tuple[Gear, ...]) -> tuple[Need, ...]:
    """The needs, those the gear meets for any team made `Given` (by its best piece); a count
    of debuff instances counts one Poison more (`Distinct.gear`)."""
    return tuple(geared(need, gear) for need in needs)


def geared(need: Need, gear: tuple[Gear, ...]) -> Need:
    match need:
        case AnyOf(tags=tags):
            meeting = tags
        case Distinct(instances=True):
            meeting = stacking_tags(need)
        case _:
            return need

    scored = [(g.ratings[t].score, g.name) for g in gear for t in meeting & g.tags]
    if not scored:
        return need

    score, name = max(scored)

    if isinstance(need, Distinct) and not need.accumulates:
        return replace(need, gear=(name, score))

    return Given(need, name, score)


def equip(kit: Kit, loadout: Loadout) -> Kit:
    """The kit with what the champion could wear only for its faction (relic skills), and
    what it's assumed to bring; each tag at its best `Rating`."""
    kind = kit.champion.type_id // 10
    worn = [g for g in loadout.gear if g.faction and g.faction == kit.champion.faction]
    extra = [(t, r) for g in worn for t, r in g.ratings.items()]
    extra += [(a.tag, ASSUMED) for a in loadout.assumed if a.champion.type_id // 10 == kind]
    if not extra:
        return kit

    counts = most_counts([kit.counts, *(g.counts for g in worn)])
    return Kit(kit.champion, best_ratings([*kit.ratings.items(), *extra]), counts)


@dataclass(frozen=True)
class GearSource:
    """Gear before it's rated: its key and name, its kind (set, relic), the faction it's
    only for, its skills, and (a relic's) the relic skill level they're at."""

    key: str
    name: str
    kind: str
    faction: str | None
    skills: tuple[int, ...]
    level: int | None = None


@dataclass(frozen=True)
class SetSource:
    """An artifact set's skills: (pieces it takes, skill id) each."""

    id: str
    name: str
    skills: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class RelicSource:
    """A relic type's skills, and those only a champion of a faction gets (display names);
    `skill_levels`: (relic level, the relic skill level it reaches), lowest first."""

    id: int
    name: str
    skills: tuple[int, ...]
    by_faction: dict[str, tuple[int, ...]]
    skill_levels: tuple[tuple[int, int], ...] = ()

    def skill_level(self, relic_level: int) -> int:
        reached = [skill for level, skill in self.skill_levels if level <= relic_level]
        return reached[-1] if reached else 1


def load_effect_sources(static: Path) -> tuple[tuple[SetSource, ...], tuple[RelicSource, ...]]:
    raw = read_json(static / "effect_sources.json")
    levels = tuple(sorted((int(k), v) for k, v in raw.get("relic_skill_levels", {}).items()))
    sets = tuple(
        SetSource(s["id"], s["name"], tuple((t["pieces"], t["skill"]) for t in s["skills"]))
        for s in raw["sets"]
    )
    relics = tuple(
        RelicSource(
            r["id"],
            r["name"],
            tuple(r["skills"]),
            {faction: tuple(ids) for faction, ids in r["by_faction"].items()},
            levels,
        )
        for r in raw["relics"]
    )
    return sets, relics


def gear_options(
    account: Account,
    sets: tuple[SetSource, ...],
    relics: tuple[RelicSource, ...],
    never: frozenset[str],
) -> list[Gear]:
    """The sets, and the relics the account has, that bring anything a team could use
    (debuffs but those in `never`: no target takes them, buffs, effects): sets by name, then
    relics."""
    sources = [
        GearSource(f"set:{s.id}", f"{s.name} set", "set", None, tuple(i for _, i in s.skills))
        for s in sorted(sets, key=lambda s: s.name)
    ]

    for relic in sorted(relics, key=lambda r: r.name):
        if relic.id in account.relic_types:
            sources += relic_sources(relic, best_level(account, relic))

    return [gear for source in sources if (gear := gear_of(account, source, never))]


def best_level(account: Account, relic: RelicSource) -> int:
    """The relic skill level of the account's best copy of the relic."""
    levels = [r.level for r in account.relic_items.values() if r.type_id == relic.id]
    return relic.skill_level(max(levels, default=0))


def relic_sources(relic: RelicSource, level: int) -> list[GearSource]:
    """A relic's skills any champion gets, then each faction's own, at relic skill `level`."""
    general = GearSource(f"relic:{relic.id}", relic.name, "relic", None, relic.skills, level)
    return [general] + [
        GearSource(
            f"relic:{relic.id}:{faction}",
            f"{relic.name} ({faction_label(faction)})",
            "relic",
            faction,
            ids,
            level,
        )
        for faction, ids in sorted(relic.by_faction.items())
    ]


def assumed_gear(tag: Tag) -> Gear:
    """Something the user assumes the whole team has (any champion could bring it)."""
    return Gear(
        f"assumed:{tag.key}", f"Assumed {plain_label(tag)}", "assumed", None, {tag: ASSUMED}
    )


def gear_of(account: Account, source: GearSource, never: frozenset[str]) -> Gear | None:
    """The gear, if its skills bring anything useful (a debuff not in `never`, a buff, an
    effect), each tag at its best `Rating` (a relic's at its level, echoes left out: they only
    add to what a champion places itself)."""
    skills = [
        at_level(s, source.level)
        for skill_id in source.skills
        if (s := account.tables.skills.get(skill_id))
    ]
    rated = [
        (tag, replace(rating, detail=f"{source.name}: {rating.detail}"))
        for skill in skills
        for tag, rating in skill_ratings(skill, 1, 1.0)
        if not (tag.side == Side.DEBUFF and tag.name in never)
    ]
    if not rated:
        return None

    counts = most_counts(skill_counts(skill) for skill in skills)
    return Gear(source.key, source.name, source.kind, source.faction, best_ratings(rated), counts)


def at_level(skill: Skill, level: int | None, echoes: bool = False) -> Skill:
    """The skill's effects at relic skill `level` (all, for a skill with no tiers or no
    level), the echoes among them or the rest."""
    placements = tuple(
        placement
        for placement in skill.placements
        if level is None or placement.relic_level in (None, level)
        if (placement.echo is not None) == echoes
    )
    return replace(skill, placements=placements)


def echoes_of(skill: Skill) -> dict[Tag, float]:
    """The chance each echoed status is placed again (the best, where several echo it)."""
    chances: dict[Tag, float] = {}

    for placement in skill.placements:
        if placement.echo:
            side = Side.DEBUFF if placement.kind == "ApplyDebuff" else Side.BUFF
            tag = Tag(side, status_kind(placement.echo))
            chances[tag] = max(chances.get(tag, 0.0), placement.chance or 1.0)

    return chances


def worn_relic(account: Account, relic: Relic, source: RelicSource, champion: Champion) -> Gear:
    """A relic one champion wears: its skills (and its faction's, for the champion's) at the
    relic's skill level, and what it echoes."""
    level = source.skill_level(relic.level)
    ids = source.skills + source.by_faction.get(faction_name(champion.faction), ())
    skills = [s for i in ids if (s := account.tables.skills.get(i))]
    own = [at_level(s, level) for s in skills]
    rated = [
        (tag, replace(rating, detail=f"{source.name}: {rating.detail}"))
        for skill in own
        for tag, rating in skill_ratings(skill, 1, 1.0)
    ]
    echoes: dict[Tag, float] = {}

    for skill in skills:
        for tag, chance in echoes_of(at_level(skill, level, echoes=True)).items():
            echoes[tag] = max(echoes.get(tag, 0.0), chance)

    counts = most_counts(skill_counts(skill) for skill in own)
    return Gear(f"worn:{relic.id}", source.name, "relic", None, best_ratings(rated), counts, echoes)


def wear(kit: Kit, worn: tuple[Gear, ...]) -> Kit:
    """The kit with the relics the champion wears: their tags at their best `Rating`, and
    the statuses they echo placed more often (its count times one plus the chance)."""
    if not worn:
        return kit

    ratings = best_ratings([*kit.ratings.items(), *(i for g in worn for i in g.ratings.items())])
    counts = dict(most_counts([kit.counts, *(g.counts for g in worn)]))

    for gear in worn:
        for tag, chance in gear.echoes.items():
            if tag in ratings:
                counts[tag] = counts.get(tag, 1) * (1 + chance)

    return Kit(kit.champion, ratings, counts)
