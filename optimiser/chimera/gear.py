"""
gear.py - what a team can wear or is assumed to have beyond its skills (`Loadout`): artifact
sets and owned relics any champion can wear (`Gear`, from `effect_sources.json`; a relic's
faction skills only for a champion of that faction), and what the user assumes. Gear any
champion can wear meets needs for any team (`Given`); faction skills and single champions'
assumptions join those champions' kits (`equip`).

- `Gear`, `Assumed`, `Loadout`, `DEFAULT_GEAR`, `ASSUMED`: what a team can wear or is
  assumed to have
- `GearSource`, `SetSource`, `RelicSource`, `load_effect_sources`, `gear_options`
  (`relic_sources`, `gear_of`), `assumed_gear`: where gear comes from
- `with_gear` (`geared`), `equip`: what it changes
"""

from dataclasses import dataclass, replace
from pathlib import Path

from optimiser.account import Account, Champion, read_json
from optimiser.chimera.kits import Kit, Rating, best_ratings, skill_ratings
from optimiser.chimera.tags import NEVER_LANDS, Side, Tag, plain_label
from optimiser.chimera.trials import AnyOf, Distinct, Given, Need, stacking_tags


@dataclass(frozen=True)
class Gear:
    """Something a champion can wear that brings buffs, debuffs or effects: an artifact set's
    skills, a relic's (`faction`: skills only a champion of that faction gets), or something
    the user assumes a team has. `ratings`: how far each can be counted on. `key` names it in
    a URL ("set:DotRate", "relic:91:Demonspawn", "assumed:buff:Shield")."""

    key: str
    name: str
    kind: str  # set, relic, assumed
    faction: str | None
    ratings: dict[Tag, Rating]

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
    """The needs, those the gear meets for any team made `Given` (by its best piece)."""
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

    return Kit(kit.champion, best_ratings([*kit.ratings.items(), *extra]))


@dataclass(frozen=True)
class GearSource:
    """Gear before it's rated: its key and name, its kind (set, relic), the faction it's
    only for, and its skills."""

    key: str
    name: str
    kind: str
    faction: str | None
    skills: tuple[int, ...]


@dataclass(frozen=True)
class SetSource:
    """An artifact set's skills: (pieces it takes, skill id) each."""

    id: str
    name: str
    skills: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class RelicSource:
    """A relic type's skills, and those only a champion of a faction gets (capture names)."""

    id: int
    name: str
    skills: tuple[int, ...]
    by_faction: dict[str, tuple[int, ...]]


def load_effect_sources(static: Path) -> tuple[tuple[SetSource, ...], tuple[RelicSource, ...]]:
    raw = read_json(static / "effect_sources.json")
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
        )
        for r in raw["relics"]
    )
    return sets, relics


def gear_options(
    account: Account, sets: tuple[SetSource, ...], relics: tuple[RelicSource, ...]
) -> list[Gear]:
    """The sets, and the relics the account has, that bring anything a trial could use
    (debuffs the Chimera takes in some form, buffs, effects): sets by name, then relics."""
    sources = [
        GearSource(f"set:{s.id}", f"{s.name} set", "set", None, tuple(i for _, i in s.skills))
        for s in sorted(sets, key=lambda s: s.name)
    ]

    for relic in sorted(relics, key=lambda r: r.name):
        if relic.id in account.relic_types:
            sources += relic_sources(relic)

    return [gear for source in sources if (gear := gear_of(account, source))]


def relic_sources(relic: RelicSource) -> list[GearSource]:
    """A relic's skills any champion gets, then each faction's own."""
    general = GearSource(f"relic:{relic.id}", relic.name, "relic", None, relic.skills)
    return [general] + [
        GearSource(
            f"relic:{relic.id}:{faction}", f"{relic.name} ({faction})", "relic", faction, ids
        )
        for faction, ids in sorted(relic.by_faction.items())
    ]


def assumed_gear(tag: Tag) -> Gear:
    """Something the user assumes the whole team has (any champion could bring it)."""
    return Gear(
        f"assumed:{tag.key}", f"Assumed {plain_label(tag)}", "assumed", None, {tag: ASSUMED}
    )


def gear_of(account: Account, source: GearSource) -> Gear | None:
    """The gear, if its skills bring anything useful (a debuff some form takes, a buff, an
    effect), each tag at its best `Rating`."""
    rated = [
        (tag, replace(rating, detail=f"{source.name}: {rating.detail}"))
        for skill_id in source.skills
        if (skill := account.tables.skills.get(skill_id))
        for tag, rating in skill_ratings(skill, 1, 1.0)
        if not (tag.side == Side.DEBUFF and tag.name in NEVER_LANDS)
    ]
    if not rated:
        return None

    return Gear(source.key, source.name, source.kind, source.faction, best_ratings(rated))
