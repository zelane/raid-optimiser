"""
account.py - the account (from the HH capture) and the game's tables (from static/), parsed
once at the boundary into the shapes the stat model and solver use.

- `Stat`, `Stats`, `Bonus`: stats, and the bonuses that raise them
- `Slot`, `ARMOUR`, `StatLine`, `Artifact`, `Champion`: what can be worn, and by whom
- `IgnoreDefence`, `FixedSet`, `VariableSet`, `ArtifactSet`: set bonuses by piece count
- `Hit`, `Skill`: champion skills, as far as damage goes
- `LoreOfSteel`, `Tables`: the game's fixed tables
- `Account`: everything a solve needs
- `DEFAULT_LEAGUE`, `AFFINITIES`, `GRADES`: what the capture's words mean
- `load_account`: the loader
- `arena_league`, `parse_tables`, `parse_sets` (`parse_ignore`), `parse_skills`,
  `parse_relics` (`relic_stats`),
  `great_hall_by_affinity`, `parse_champion`, `parse_artifact` (`parse_line`): its steps
- `parse_bonus`, `parse_bonuses`, `parse_levels`: what the steps share
"""

import json
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path


class Stat(StrEnum):
    """The stats gear changes, by the game's names; members are the short names."""

    HP = "Health"
    ATK = "Attack"
    DEF = "Defence"
    SPD = "Speed"
    RES = "Resistance"
    ACC = "Accuracy"
    CR = "CriticalChance"
    CD = "CriticalDamage"


type Stats = dict[Stat, float]


@dataclass(frozen=True)
class Bonus:
    """A stat bonus: a flat amount, or a fraction (0.1 is 10 %)."""

    stat: Stat
    value: float
    absolute: bool


class Slot(Enum):
    WEAPON = "Weapon"
    HELMET = "Helmet"
    SHIELD = "Shield"
    GLOVES = "Gloves"
    CHEST = "Chest"
    BOOTS = "Boots"
    RING = "Ring"
    AMULET = "Cloak"
    BANNER = "Banner"


ARMOUR = (Slot.WEAPON, Slot.HELMET, Slot.SHIELD, Slot.GLOVES, Slot.CHEST, Slot.BOOTS)


@dataclass(frozen=True)
class StatLine:
    """A stat line as the game shows it. `stat` is None for lines gear optimising ignores
    (damage dealt/taken); `kind` is the game's name either way."""

    kind: str
    stat: Stat | None
    value: float
    absolute: bool
    glyph: float = 0
    rolls: int = 0

    def bonus(self) -> Bonus | None:
        return Bonus(self.stat, self.value + self.glyph, self.absolute) if self.stat else None


@dataclass(frozen=True)
class Artifact:
    """A piece of gear. `faction` is set on accessories only that faction can wear."""

    id: int
    slot: Slot
    set_id: int
    rank: int
    rarity: str
    level: int
    primary: StatLine
    substats: tuple[StatLine, ...]
    ascension: StatLine | None
    faction: str | None

    def lines(self) -> tuple[StatLine, ...]:
        return (self.primary, *self.substats, *([self.ascension] if self.ascension else []))


@dataclass(frozen=True)
class Champion:
    id: int
    name: str
    type_id: int
    faction: str
    element: str  # affinity: Magic, Force, Spirit, Void
    rarity: str
    grade: int
    level: int
    awakening: int
    empower: int
    masteries: frozenset[int]
    artifact_ids: tuple[int, ...]
    relics: tuple[Bonus, ...]  # the stats of the relics it wears
    great_hall: tuple[Bonus, ...]  # the account's Great Hall, for the champion's affinity
    skill_levels: dict[int, int]  # skill id -> level (1 + books used)


@dataclass(frozen=True)
class IgnoreDefence:
    """A set's ignore-DEF passive, as a fraction (0.25 ignores 25 %). Sets granting the same
    skill don't stack unless `per_set` (Cruel); `aoe_only` applies to AoE skills only."""

    skill_id: int
    value: float
    per_set: bool
    aoe_only: bool


@dataclass(frozen=True)
class FixedSet:
    """A set whose bonus counts once per `pieces` pieces worn."""

    id: int
    name: str
    pieces: int
    bonuses: tuple[Bonus, ...]
    ignore: tuple[IgnoreDefence, ...]


@dataclass(frozen=True)
class VariableSet:
    """A set whose bonus grows with each piece: the total at each piece count."""

    id: int
    name: str
    totals: dict[int, tuple[Bonus, ...]]
    ignore_at: dict[int, tuple[IgnoreDefence, ...]]  # piece count -> ignore-DEF passives


type ArtifactSet = FixedSet | VariableSet


@dataclass(frozen=True)
class Hit:
    """One unconditional damage effect of a skill: `formula` is the game's multiplier text
    (e.g. "4.5*ATK"), applied `count` times; `defence_modifier` < 0 ignores DEF."""

    formula: str
    count: int
    defence_modifier: float


@dataclass(frozen=True)
class Skill:
    id: int
    name: str
    group: str  # Active, Passive, ...
    aoe: bool
    hits: tuple[Hit, ...]
    book_damage: tuple[float, ...]  # per book, in order; level L has the first L-1


@dataclass(frozen=True)
class LoreOfSteel:
    """The mastery that scales artifact set stat bonuses."""

    mastery_id: int
    multiplier: float


@dataclass(frozen=True)
class Tables:
    """The game's fixed tables. Unscaled stats are as the static data holds them (HP / 15,
    crit in %); `level_curve` scales them for ranks below 6* L60. The arena bonus is the
    account's league."""

    base_6_60: dict[int, Stats]
    unscaled: dict[int, Stats]
    level_curve: dict[tuple[int, int], float]
    great_hall: dict[Stat, tuple[Bonus, ...]]  # stat -> the bonus at each level (1 first)
    arena: tuple[Bonus, ...]  # the account's classic arena league
    empower: dict[str, list[tuple[Bonus, ...]]]
    awakening: dict[str, list[tuple[Bonus, ...]]]
    masteries: dict[int, Bonus]
    lore_of_steel: LoreOfSteel
    sets: dict[int, ArtifactSet]
    skills: dict[int, Skill]
    hero_skills: dict[int, tuple[int, ...]]  # hero type id -> its skill ids (first form)


@dataclass(frozen=True)
class Account:
    user_id: int  # the Raid account
    champions: dict[int, Champion]
    artifacts: tuple[Artifact, ...]
    owners: dict[int, int]  # artifact id -> id of the champion wearing it
    tables: Tables


DEFAULT_LEAGUE = "GoldV"  # if the capture doesn't say
AFFINITIES = ("Magic", "Force", "Spirit", "Void")

GRADES = {
    "OneStar": 1,
    "TwoStars": 2,
    "ThreeStars": 3,
    "FourStars": 4,
    "FiveStars": 5,
    "SixStars": 6,
}


def load_account(captures: Path, static: Path, schema: Path) -> Account:
    """The latest capture and the static tables, in one place."""
    account = read_json(captures / "account.json")
    tables = parse_tables(static, schema, arena_league(account))
    relics = parse_relics(account["Relics"], read_json(static / "bonuses.json")["relics"])
    great_hall = great_hall_by_affinity(account.get("GreatHall"), tables)
    champions = [
        parse_champion(raw, relics, great_hall) for raw in read_json(captures / "champions.json")
    ]
    hh_set_ids = read_json(captures / "set_ids.json")
    artifacts = tuple(
        parse_artifact(raw, hh_set_ids) for raw in read_json(captures / "artifacts.json")
    )
    owners = {art_id: c.id for c in champions for art_id in c.artifact_ids}

    return Account(
        user_id=account["UserId"],
        champions={c.id: c for c in champions},
        artifacts=artifacts,
        owners=owners,
        tables=tables,
    )


def great_hall_by_affinity(
    levels: dict[str, dict[str, int]] | None, tables: Tables
) -> dict[str, tuple[Bonus, ...]]:
    """Affinity -> its Great Hall bonuses at the account's levels. Without levels in the
    capture, every affinity is taken as complete."""
    by_stat = tables.great_hall
    complete = tuple(bonuses[-1] for bonuses in by_stat.values())

    if not levels:
        return {affinity: complete for affinity in AFFINITIES}

    return {
        affinity: tuple(
            by_stat[Stat(stat)][level - 1]
            for stat, level in stat_levels.items()
            if stat in Stat and level > 0
        )
        for affinity, stat_levels in levels.items()
    }


def parse_relics(relics: list[dict], table: dict) -> dict[int, tuple[Bonus, ...]]:
    """Relic id -> the stats it gives."""
    return {relic["Id"]: relic_stats(relic, table) for relic in relics}


def relic_stats(relic: dict, table: dict) -> tuple[Bonus, ...]:
    """Each of the relic type's stats that its level has unlocked, valued by the levels
    gained since it unlocked (a stat opening at 9 gives its first value at level 9).
    Stones add skills, not stats."""
    stats = table["types"].get(str(relic["TypeId"]), {}).get("stats", [])
    level = relic["Level"]
    # A type may have fewer stats than there are opening levels.
    openings = zip(stats, table["opening_levels"], strict=False)
    at_level = {
        stat: table["values"][stat][level - opens] for stat, opens in openings if level >= opens
    }
    return tuple(
        bonus
        for stat, value in at_level.items()
        if (bonus := parse_bonus(stat, value["value"], value["absolute"]))
    )


def parse_champion(
    raw: dict, relics: dict[int, tuple[Bonus, ...]], great_hall: dict[str, tuple[Bonus, ...]]
) -> Champion:
    return Champion(
        id=raw["Id"],
        name=raw["Name"] or f"type {raw['TypeId']}",
        type_id=raw["TypeId"],
        faction=raw["Faction"],
        element=raw["Element"],
        rarity=raw["Rarity"],
        grade=GRADES[raw["Grade"]],
        level=raw["Level"],
        awakening=GRADES.get(raw["AwakenedGrade"], 0),
        empower=raw["EmpowerLevel"],
        masteries=frozenset(raw["Masteries"] or ()),
        artifact_ids=tuple(raw["Artifacts"] or ()),
        relics=tuple(
            bonus for relic_id in raw["Relics"] or () for bonus in relics.get(relic_id, ())
        ),
        great_hall=great_hall.get(raw["Element"], ()),
        skill_levels={
            int(skill_id): level for skill_id, level in (raw["SkillLevels"] or {}).items()
        },
    )


def parse_artifact(raw: dict, hh_set_ids: dict[str, int]) -> Artifact:
    return Artifact(
        id=raw["Id"],
        slot=Slot(raw["Kind"]),
        set_id=hh_set_ids[raw["Set"]],
        rank=GRADES[raw["Rank"]],
        rarity=raw["Rarity"],
        level=raw["Level"],
        primary=parse_line(raw["PrimaryBonus"]),
        substats=tuple(parse_line(sub) for sub in raw["SecondaryBonuses"]),
        ascension=parse_line(raw["AscendBonus"]) if raw["AscendBonus"] else None,
        faction=None if raw["RequiredFraction"] == "None" else raw["RequiredFraction"],
    )


def parse_line(raw: dict) -> StatLine:
    kind = raw["Kind"]
    return StatLine(
        kind=kind,
        stat=Stat(kind) if kind in Stat else None,
        value=raw["Value"],
        absolute=raw["IsAbsolute"],
        glyph=raw["Enhancement"],
        rolls=raw["Level"],
    )


def parse_sets(static: Path, set_numbers: dict[str, int]) -> dict[int, ArtifactSet]:
    sets: dict[int, ArtifactSet] = {}

    for raw in read_json(static / "sets.json"):
        if raw["placeholder_text"]:
            continue  # unreleased: the game ships developer text, and no one can own one yet

        set_id = set_numbers[raw["id"]]
        totals = {
            tier["pieces"]: tuple(
                bonus
                for s in tier["stats"]
                if (bonus := parse_bonus(s["stat"], s["value"], s["absolute"]))
            )
            for tier in raw["tiers"]
        }

        ignore = {tier["pieces"]: parse_ignore(tier["ignore_defence"]) for tier in raw["tiers"]}

        if raw["variable"]:
            sets[set_id] = VariableSet(set_id, raw["name"], totals, ignore)
        else:
            pieces = raw["pieces"]
            sets[set_id] = FixedSet(set_id, raw["name"], pieces, totals[pieces], ignore[pieces])

    return sets


def parse_ignore(raw: list[dict]) -> tuple[IgnoreDefence, ...]:
    return tuple(IgnoreDefence(i["skill"], i["value"], i["per_set"], i["aoe_only"]) for i in raw)


def parse_skills(static: Path) -> dict[int, Skill]:
    return {
        int(skill_id): Skill(
            id=int(skill_id),
            name=raw["name"] or f"skill {skill_id}",
            group=raw["group"],
            aoe=raw["aoe"],
            hits=tuple(Hit(h["formula"], h["count"], h["defence_modifier"]) for h in raw["hits"]),
            book_damage=tuple(raw["book_damage"]),
        )
        for skill_id, raw in read_json(static / "skills.json").items()
    }


def arena_league(account: dict) -> str:
    league = account.get("ArenaLeague")
    return league if league and league != "None" else DEFAULT_LEAGUE


def parse_tables(static: Path, schema: Path, league: str) -> Tables:
    set_kinds = read_json(schema)["enums"]["ArtifactSetKindId"]
    bonuses = read_json(static / "bonuses.json")
    lore = next(
        (int(mastery_id), m["set_bonus_multiplier"])
        for mastery_id, m in bonuses["masteries"].items()
        if "set_bonus_multiplier" in m
    )
    hero_types = read_json(static / "hero_types.json")

    return Tables(
        base_6_60={
            int(type_id): {Stat(k): v for k, v in forms[0].items() if k in Stat}
            for type_id, forms in read_json(static / "base_stats_6_60.json").items()
        },
        unscaled={
            t["id"]: {Stat(k): v for k, v in t["forms"][0]["base_stats"].items() if k in Stat}
            for t in hero_types
            if t["forms"]
        },
        level_curve={
            (int(grade), int(level)): multiplier
            for grade, levels in read_json(static / "level_curve.json").items()
            for level, multiplier in levels.items()
        },
        great_hall={
            Stat(stat): tuple(Bonus(Stat(stat), x["value"], x["absolute"]) for x in levels)
            for stat, levels in bonuses["great_hall"].items()
            if stat in Stat
        },
        arena=parse_bonuses(bonuses["arena"][league]),
        empower=parse_levels(bonuses["empower"]),
        awakening=parse_levels(bonuses["awakening"]),
        masteries={
            int(mastery_id): bonus
            for mastery_id, m in bonuses["masteries"].items()
            if "stat" in m and (bonus := parse_bonus(m["stat"], m["value"], m["absolute"]))
        },
        lore_of_steel=LoreOfSteel(*lore),
        sets=parse_sets(static, {name: int(number) for number, name in set_kinds.items()}),
        skills=parse_skills(static),
        hero_skills={t["id"]: tuple(t["forms"][0]["skills"]) for t in hero_types if t["forms"]},
    )


def parse_levels(by_rarity: dict) -> dict[str, list[tuple[Bonus, ...]]]:
    """Per rarity, the cumulative bonuses at each level (index 0 is level 1)."""
    return {
        rarity: [parse_bonuses(level) for level in levels] for rarity, levels in by_rarity.items()
    }


def parse_bonuses(by_stat: dict) -> tuple[Bonus, ...]:
    """Bonuses from {stat: {value, absolute}}, skipping stats gear doesn't change."""
    return tuple(
        bonus
        for stat, raw in by_stat.items()
        if (bonus := parse_bonus(stat, raw["value"], raw["absolute"]))
    )


def parse_bonus(stat: str, value: float, absolute: bool) -> Bonus | None:
    """None for stats the optimiser ignores (damage dealt/taken, crit heal, ignore DEF)."""
    return Bonus(Stat(stat), value, absolute) if stat in Stat else None


def read_json(path: Path):
    with path.open() as file:
        return json.load(file)
