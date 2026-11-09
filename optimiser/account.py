"""
account.py - the account (from the HH capture) and the game's tables (`paths.GAME`), parsed
once at the boundary into the shapes the stat model and solver use.

- `Stat`, `STAT_NAMES`, `Stats`, `Bonus`: stats (by the game's names), and the bonuses that
  raise them
- `Slot`, `ARMOUR`, `StatLine`, `Artifact`, `Champion`: what can be worn, and by whom
- `LOCK_LEVELS`, `Locks`: champion locks, which keep gear on its champion
- `GlyphKind`, `GlyphGrade`: glyphs, by the stat they raise and how strong they are
- `GearLine`, `GearTables`: gear stats by level and by ascension level
- `IgnoreDefence`, `FixedSet`, `VariableSet`, `ArtifactSet`: set bonuses by piece count
- `Hit`, `Effect`, `Skill`: champion skills, as far as damage (and what else scales) goes
- `HeroForm`, `LoreOfSteel`, `EmpowerSubstitute`, `Tables`: the game's fixed tables
- `Account`: everything a solve needs
- `DEFAULT_LEAGUE`, `AFFINITIES`, `GRADES`, `GLYPH_RARITIES`: what the game's words mean
- `load_account`: the loader
- `worn_gear`: what a champion wears
- `arena_league`, `cached_tables` (`tables_stamp`), `parse_tables`, `parse_sets`
  (`parse_ignore`), `parse_skills`, `parse_relics` (`relic_stats`), `parse_forms`,
  `parse_glyphs`, `parse_gear` (`by_line`), `great_hall_by_affinity`, `parse_champion`,
  `parse_artifact` (`parse_line`): its steps
- `parse_bonus`, `parse_bonuses`, `parse_levels`: what the steps share
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum
from functools import lru_cache
from pathlib import Path

import orjson


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


STAT_NAMES: dict[str, Stat] = {stat.value: stat for stat in Stat}  # `in Stat` is slow


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
    (damage dealt/taken); `kind` is the game's name either way. `glyph` is the glyph on it
    now; `planned_glyph` one assumed applied, set only when it beats `glyph`. `planned_value`
    is the value assumed once the piece is levelled or ascended further."""

    kind: str
    stat: Stat | None
    value: float
    absolute: bool
    glyph: float = 0
    rolls: int = 0
    planned_glyph: float = 0
    planned_value: float | None = None

    def bonus(self) -> Bonus | None:
        if self.stat is None:
            return None

        value = self.value if self.planned_value is None else self.planned_value
        return Bonus(self.stat, value + max(self.glyph, self.planned_glyph), self.absolute)


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
    ascend_level: int  # stars ascended, 0 to `rank`
    faction: str | None
    reworked: bool = False  # its substats re-picked in the Forge, which only happens once
    variant: str = "Normal"  # the game's; "Corrupted" pieces have unusual stats and a border
    planned_level: int | None = None  # assumed levelled to this (main stat only)
    planned_ascend_level: int | None = None  # assumed ascended to this

    def special(self) -> bool:
        return self.variant != "Normal"

    def lines(self) -> tuple[StatLine, ...]:
        return (self.primary, *self.substats, *([self.ascension] if self.ascension else []))


@dataclass(frozen=True)
class Champion:
    id: int
    name: str
    type_id: int
    faction: str
    element: str  # affinity: Magic, Force, Spirit, Void
    role: str  # the game's: Attack, Defense, Health, Support
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
    # Which of its forms (`Tables.hero_forms`) it's taken in, 0 first: mythicals have two, and
    # each has its own base stats and skills. A playable form never changes affinity, so the
    # Great Hall doesn't depend on it. The capture doesn't say; a request does.
    form: int = 0

    @property
    def ascension(self) -> int:
        """0 to 6: the type id's last digit (each ascension is a type of its own)."""
        return self.type_id % 10


LOCK_LEVELS = range(1, 6)  # 5 the strongest

# Champion id -> lock level. A lock keeps a champion's gear out of solves that only allow gear
# from champions locked below some level; unlocked champions are absent (0).
type Locks = Mapping[int, int]


@dataclass(frozen=True)
class GlyphKind:
    """What a glyph raises: HP flat and HP % are different glyphs."""

    stat: Stat
    absolute: bool


@dataclass(frozen=True)
class GlyphGrade:
    """How strong a glyph is: ranks 1-5 come in Uncommon only, 6 in Uncommon to Legendary."""

    rank: int
    rarity: str


@dataclass(frozen=True)
class GearLine:
    """A main stat or ascension bonus, by the slot it's on."""

    slot: Slot
    stat: Stat
    absolute: bool


@dataclass(frozen=True)
class GearTables:
    """`primary`: main stat at each level (0 first), by rank. `ascension`: the ascension
    bonus at each ascension level (1 first), by rank. Rarity changes neither."""

    max_level: int
    primary: dict[GearLine, dict[int, tuple[float, ...]]]
    ascension: dict[GearLine, dict[int, tuple[float, ...]]]


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
class Effect:
    """A skill effect other than damage whose size scales with the caster's stats: `kind` is
    the game's (Heal, ApplyBuff for shields, Revive, ApplyDebuff for bombs)."""

    kind: str
    formula: str


@dataclass(frozen=True)
class Skill:
    id: int
    name: str
    group: str  # Active, Passive, ...
    aoe: bool
    hits: tuple[Hit, ...]
    book_damage: tuple[float, ...]  # per book, in order; level L has the first L-1
    scaling: tuple[Effect, ...] = ()


@dataclass(frozen=True)
class HeroForm:
    """One of a champion type's forms (mythicals have two): its role as the game names it
    (Attack, Defense, Health, Support), its skills, and its base stats as the static data
    holds them (HP / 15, crit in %; `levels` scales them)."""

    role: str
    skills: tuple[int, ...]
    unscaled: Stats


@dataclass(frozen=True)
class LoreOfSteel:
    """The mastery that scales artifact set stat bonuses."""

    mastery_id: int
    multiplier: float


@dataclass(frozen=True)
class EmpowerSubstitute:
    """The champion whose copies empower one only obtainable once (`Tables`)."""

    type_id: int  # ascension 0
    name: str


@dataclass(frozen=True)
class Tables:
    """The game's fixed tables. The arena bonus is the account's league."""

    great_hall: dict[Stat, tuple[Bonus, ...]]  # stat -> the bonus at each level (1 first)
    arena: tuple[Bonus, ...]  # the account's classic arena league
    empower: dict[str, list[tuple[Bonus, ...]]]
    # Champions only obtainable once (hero type id, ascension 0) -> the champion whose copies
    # empower them instead of duplicates.
    empower_substitutes: dict[int, EmpowerSubstitute]
    awakening: dict[str, list[tuple[Bonus, ...]]]
    masteries: dict[int, Bonus]
    lore_of_steel: LoreOfSteel
    sets: dict[int, ArtifactSet]
    skills: dict[int, Skill]
    hero_forms: dict[int, tuple[HeroForm, ...]]  # hero type id -> every form, first first
    glyphs: dict[GlyphKind, dict[GlyphGrade, float]]  # each grade's top roll, weakest first
    gear: GearTables

    def form_of(self, champion: Champion) -> HeroForm:
        """The form the champion is in (`Champion.form`)."""
        return self.hero_forms[champion.type_id][champion.form]

    def skills_of(self, champion: Champion) -> tuple[int, ...]:
        """The champion's skill ids, in the form they're in; none if the type is unknown."""
        forms = self.hero_forms.get(champion.type_id, ())
        return forms[champion.form].skills if champion.form < len(forms) else ()


@dataclass(frozen=True)
class Account:
    """`mailbox`: gear that overflowed the inventory, waiting in the mailbox to be claimed."""

    user_id: int  # the Raid account
    champions: dict[int, Champion]
    artifacts: tuple[Artifact, ...]
    owners: dict[int, int]  # artifact id -> id of the champion wearing it
    tables: Tables
    mailbox: tuple[Artifact, ...] = ()


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
GLYPH_RARITIES = ("Uncommon", "Rare", "Epic", "Legendary")


def load_account(captures: Path, static: Path, schema: Path) -> Account:
    """The latest capture and the static tables, in one place."""
    account = read_json(captures / "account.json")
    tables = cached_tables(static, schema, arena_league(account), tables_stamp(static, schema))
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
    mailbox = tuple(
        parse_artifact(raw, hh_set_ids)
        for item in account.get("InboxItems") or ()
        for raw in item.get("Artifacts") or ()
    )

    return Account(
        user_id=account["UserId"],
        champions={c.id: c for c in champions},
        artifacts=artifacts,
        owners=owners,
        tables=tables,
        mailbox=mailbox,
    )


def worn_gear(account: Account, champion: Champion) -> list[Artifact]:
    """What the champion wears now."""
    worn = set(champion.artifact_ids)
    return [artifact for artifact in account.artifacts if artifact.id in worn]


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
            by_stat[STAT_NAMES[stat]][level - 1]
            for stat, level in stat_levels.items()
            if stat in STAT_NAMES and level > 0
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
        role=raw.get("Role") or "",
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
        ascend_level=raw.get("AscendLevel") or 0,
        faction=None if raw["RequiredFraction"] == "None" else raw["RequiredFraction"],
        reworked=bool(raw.get("RerollsCount")),
        variant=raw.get("VariantId") or "Normal",
    )


def parse_line(raw: dict) -> StatLine:
    kind = raw["Kind"]
    return StatLine(
        kind=kind,
        stat=STAT_NAMES.get(kind),
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
            scaling=tuple(Effect(e["kind"], e["formula"]) for e in raw.get("scaling", ())),
        )
        for skill_id, raw in read_json(static / "skills.json").items()
    }


def arena_league(account: dict) -> str:
    league = account.get("ArenaLeague")
    return league if league and league != "None" else DEFAULT_LEAGUE


@lru_cache(maxsize=2)
def cached_tables(static: Path, schema: Path, league: str, stamp: tuple[int, ...]) -> Tables:
    """`parse_tables`, reparsed only when a game update rewrites the tables (`stamp`, only
    the cache key: `tables_stamp`), not with each capture."""
    return parse_tables(static, schema, league)


def tables_stamp(static: Path, schema: Path) -> tuple[int, ...]:
    return tuple(path.stat().st_mtime_ns for path in (schema, *sorted(static.glob("*.json"))))


def parse_tables(static: Path, schema: Path, league: str) -> Tables:
    set_kinds = read_json(schema)["enums"]["ArtifactSetKindId"]
    bonuses = read_json(static / "bonuses.json")
    lore = next(
        (int(mastery_id), m["set_bonus_multiplier"])
        for mastery_id, m in bonuses["masteries"].items()
        if "set_bonus_multiplier" in m
    )
    hero_types = read_json(static / "hero_types.json")
    names = {t["id"]: t["name"] for t in hero_types}

    return Tables(
        great_hall={
            Stat(stat): tuple(Bonus(Stat(stat), x["value"], x["absolute"]) for x in levels)
            for stat, levels in bonuses["great_hall"].items()
            if stat in Stat
        },
        arena=parse_bonuses(bonuses["arena"][league]),
        empower=parse_levels(bonuses["empower"]),
        empower_substitutes={
            int(type_id): EmpowerSubstitute(substitute, names[substitute])
            for type_id, substitute in bonuses["empower_substitutes"].items()
        },
        awakening=parse_levels(bonuses["awakening"]),
        masteries={
            int(mastery_id): bonus
            for mastery_id, m in bonuses["masteries"].items()
            if "stat" in m and (bonus := parse_bonus(m["stat"], m["value"], m["absolute"]))
        },
        lore_of_steel=LoreOfSteel(*lore),
        sets=parse_sets(static, {name: int(number) for number, name in set_kinds.items()}),
        skills=parse_skills(static),
        hero_forms={t["id"]: parse_forms(t["forms"]) for t in hero_types},
        glyphs=parse_glyphs(read_json(static / "glyphs.json")),
        gear=parse_gear(read_json(static / "gear.json")),
    )


def parse_forms(forms: list[dict]) -> tuple[HeroForm, ...]:
    return tuple(
        HeroForm(
            role=form["role"],
            skills=tuple(form["skills"]),
            unscaled={STAT_NAMES[k]: v for k, v in form["base_stats"].items() if k in STAT_NAMES},
        )
        for form in forms
    )


def parse_gear(raw: dict) -> GearTables:
    return GearTables(
        max_level=raw["max_level"],
        primary=by_line(raw["primary"]),
        ascension=by_line(raw["ascension"]),
    )


def by_line(tables: list[dict]) -> dict[GearLine, dict[int, tuple[float, ...]]]:
    """Each table under every slot it applies to; stats gear optimising ignores are left out."""
    return {
        GearLine(Slot(slot), Stat(table["stat"]), table["absolute"]): {
            int(rank): tuple(values) for rank, values in table["values"].items()
        }
        for table in tables
        if table["stat"] in Stat
        for slot in table["slots"]
    }


def parse_glyphs(glyphs: list[dict]) -> dict[GlyphKind, dict[GlyphGrade, float]]:
    """Kinds in the game's stat order, flat before %; each kind's grades weakest first."""
    by_kind: dict[GlyphKind, dict[GlyphGrade, float]] = {}

    def order(raw: dict) -> tuple:
        stat = list(Stat).index(Stat(raw["stat"]))
        return stat, not raw["absolute"], raw["rank"], GLYPH_RARITIES.index(raw["rarity"])

    for raw in sorted(glyphs, key=order):
        kind = GlyphKind(Stat(raw["stat"]), raw["absolute"])
        by_kind.setdefault(kind, {})[GlyphGrade(raw["rank"], raw["rarity"])] = raw["max"]

    return by_kind


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
    return Bonus(STAT_NAMES[stat], value, absolute) if stat in STAT_NAMES else None


def read_json(path: Path):
    return orjson.loads(path.read_bytes())
