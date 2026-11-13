"""
account.py - the account (the memory reader's snapshot, `paths.SNAPSHOT`) and the game's
tables (`paths.GAME`), parsed once at the boundary into the shapes the stat model and solver use.

- `Stat`, `STAT_NAMES`, `Stats`, `Bonus`: stats (by the game's names), and the bonuses that
  raise them
- `Slot`, `ARMOUR`, `StatLine`, `Artifact`, `Champion`: what can be worn, and by whom
- `LOCK_LEVELS`, `Locks`: champion locks, which keep gear on its champion
- `GlyphKind`, `GlyphGrade`: glyphs, by the stat they raise and how strong they are
- `GearLine`, `GearTables`: gear stats by level and by ascension level
- `IgnoreDefence`, `FixedSet`, `VariableSet`, `ArtifactSet`: set bonuses by piece count
- `Hit`, `Effect`, `Placement`, `Book`, `Skill`: champion skills, as far as damage (and what
  else scales) and what they place and do (how often, how surely, on whom) go
- `HeroForm`, `HeroType`, `LoreOfSteel`, `EmpowerSubstitute`, `Tables`: the game's fixed tables
- `Preset`, `GearPreset`, `ChimeraRaid`: saved teams, global gear presets, and the Chimera's
  current raid
- `Account`: everything a solve needs, and the account's saved teams
- `DEFAULT_LEAGUE`, `AFFINITIES`, `GLYPH_RARITIES`, `FACTION_NAMES`, `NO_FACTION`,
  `faction_name`: what the game's words mean
- `load_account`: the loader
- `worn_gear`: what a champion wears
- `cached_tables` (`tables_stamp`), `parse_tables`, `parse_sets` (`parse_ignore`),
  `parse_skills`, `parse_relics` (`relic_stats`), `parse_hero_type`, `parse_forms`,
  `parse_glyphs`, `parse_gear` (`by_line`), `great_hall_by_affinity`, `parse_champion`,
  `parse_artifact` (`parse_line`), `parse_preset`, `parse_gear_preset`, `parse_raid`, `team`:
  its steps
- `parse_bonus`, `parse_bonuses`, `parse_levels`: what the steps share
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
    marker: str = "None"  # its tag in game (`HeroMarker`: Favorite, ArenaFirst, …), at most one
    # Which of its forms (`Tables.hero_forms`) it's taken in, 0 first: mythicals have two, and
    # each has its own base stats and skills. A playable form never changes affinity, so the
    # Great Hall doesn't depend on it. The game doesn't say; a request does.
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
class Placement:
    """One effect of a skill: its kind (ApplyBuff, ApplyDebuff, Revive, …), the status it
    places (None for other kinds) and for how many turns, its chance (None: always), who it
    lands on (the game's target type), whether it happens against a boss (`on_boss`: True
    always, False never, None when a condition decides), and whether it can't be resisted."""

    kind: str
    status: str | None
    turns: int | None
    chance: float | None
    target: str
    on_boss: bool | None
    unresistable: bool


@dataclass(frozen=True)
class Book:
    """What a skill book adds: its type (Attack, EffectChance, CooltimeTurn, …) and value."""

    type: str
    value: float


@dataclass(frozen=True)
class Skill:
    """`debuffs` (on enemies) and `buffs` (on its team) are status effect names, whatever the
    chance or condition; `effect_kinds` every effect kind the skill has (Revive, TeamAttack,
    PassiveCounterattack, …); `target_hp_damage`: it hits for a share of the target's HP;
    `placements` how each effect lands, `books` what each book adds (level L has the first
    L-1), `cooldown` in turns (0: every turn)."""

    id: int
    name: str
    group: str  # Active, Passive, ...
    aoe: bool
    hits: tuple[Hit, ...]
    book_damage: tuple[float, ...]  # per book, in order; level L has the first L-1
    scaling: tuple[Effect, ...] = ()
    debuffs: frozenset[str] = frozenset()
    buffs: frozenset[str] = frozenset()
    effect_kinds: frozenset[str] = frozenset()
    target_hp_damage: bool = False
    cooldown: int = 0
    placements: tuple[Placement, ...] = ()
    books: tuple[Book, ...] = ()


@dataclass(frozen=True)
class HeroForm:
    """One of a champion type's forms (mythicals have two): its role as the game names it
    (Attack, Defense, Health, Support), its skills, and its base stats as the static data
    holds them (HP / 15, crit in %; `levels` scales them)."""

    role: str
    skills: tuple[int, ...]
    unscaled: Stats


@dataclass(frozen=True)
class HeroType:
    """A champion type's fixed facts, by the game's names but for the faction (its display
    name, `faction_name`); affinity and role are its first form's (a form never changes
    affinity)."""

    name: str
    faction: str
    rarity: str
    element: str
    role: str


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
    hero_types: dict[int, HeroType]
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
class Preset:
    """A saved team: `area` is the game's preset type (Pvp for arena attack, Chimera, Hydra,
    DoomTower, …)."""

    id: int
    name: str
    area: str
    champion_ids: tuple[int, ...]


@dataclass(frozen=True)
class GearPreset:
    """A global gear preset: pieces saved together under a name, for any champion to put on
    (an artifact preset, or an accessory one)."""

    id: int
    name: str
    accessories: bool
    artifact_ids: tuple[int, ...]


@dataclass(frozen=True)
class ChimeraRaid:
    """The Chimera's current raid; its prize offset decides which trials give which rewards
    (`optimiser.chimera.rotation`)."""

    start: datetime
    number: int
    prize_offset: int


@dataclass(frozen=True)
class Account:
    """`mailbox`: gear that overflowed the inventory, waiting in the mailbox to be claimed;
    `relic_types`: the relic types the account has (worn or not); `presets`, the arena
    defenses (classic, and 3v3's three teams), `gear_presets` (the global ones; champions' own
    presets are left out) and `chimera_raid`: what the game holds besides gear."""

    user_id: int  # the Raid account
    champions: dict[int, Champion]
    artifacts: tuple[Artifact, ...]
    owners: dict[int, int]  # artifact id -> id of the champion wearing it
    tables: Tables
    mailbox: tuple[Artifact, ...] = ()
    relic_types: frozenset[int] = frozenset()
    presets: tuple[Preset, ...] = ()
    arena_defense: tuple[int, ...] = ()
    arena3x3_defense: tuple[tuple[int, ...], ...] = ()
    gear_presets: tuple[GearPreset, ...] = ()
    chimera_raid: ChimeraRaid | None = None


DEFAULT_LEAGUE = "GoldV"  # if the game doesn't say
AFFINITIES = ("Magic", "Force", "Spirit", "Void")
GLYPH_RARITIES = ("Uncommon", "Rare", "Epic", "Legendary")
# The factions the game shows under another name than its own (the art is named by these)
FACTION_NAMES = {"Samurai": "Shadowkin", "Olympians": "Argonites"}
NO_FACTION = "Unknown"  # a piece any faction can wear


def faction_name(game_name: str) -> str:
    return FACTION_NAMES.get(game_name, game_name)


def load_account(snapshot: Path, static: Path, schema: Path) -> Account:
    """The latest snapshot and the static tables, in one place."""
    account = read_json(snapshot)
    league = account["arena_league"] or DEFAULT_LEAGUE
    tables = cached_tables(static, schema, league, tables_stamp(static, schema))
    relics = parse_relics(account["relics"], read_json(static / "bonuses.json")["relics"])
    great_hall = great_hall_by_affinity(account["great_hall"], tables)
    champions = [
        parse_champion(
            raw,
            tables.hero_types[raw["type_id"]],
            account["equipped"].get(str(raw["id"]), ()),
            tuple(
                bonus
                for relic_id in account["worn_relics"].get(str(raw["id"]), ())
                for bonus in relics.get(relic_id, ())
            ),
            great_hall,
        )
        for raw in account["heroes"]
    ]
    owners = {art_id: c.id for c in champions for art_id in c.artifact_ids}
    mailbox = tuple(parse_artifact(raw) for item in account["inbox"] for raw in item["artifacts"])

    return Account(
        user_id=account["user_id"],
        champions={c.id: c for c in champions},
        artifacts=tuple(parse_artifact(raw) for raw in account["artifacts"]),
        owners=owners,
        tables=tables,
        mailbox=mailbox,
        relic_types=frozenset(relic["type_id"] for relic in account["relics"]),
        presets=tuple(parse_preset(raw) for raw in account["presets"]),
        arena_defense=team(account["arena_defense"]),
        arena3x3_defense=tuple(team(raw) for raw in account["arena3x3_defense"]),
        gear_presets=tuple(
            parse_gear_preset(raw) for raw in account["gear_presets"] if raw["hero_id"] is None
        ),
        chimera_raid=parse_raid(account["chimera"]) if account["chimera"] else None,
    )


def worn_gear(account: Account, champion: Champion) -> list[Artifact]:
    """What the champion wears now."""
    worn = set(champion.artifact_ids)
    return [artifact for artifact in account.artifacts if artifact.id in worn]


def great_hall_by_affinity(
    levels: dict[str, dict[str, int]], tables: Tables
) -> dict[str, tuple[Bonus, ...]]:
    """Affinity -> its Great Hall bonuses at the account's levels. Without any levels (the
    game hasn't loaded them), every affinity is taken as complete."""
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
    return {relic["id"]: relic_stats(relic, table) for relic in relics}


def relic_stats(relic: dict, table: dict) -> tuple[Bonus, ...]:
    """Each of the relic type's stats that its level has unlocked, valued by the levels
    gained since it unlocked (a stat opening at 9 gives its first value at level 9).
    Stones add skills, not stats."""
    stats = table["types"].get(str(relic["type_id"]), {}).get("stats", [])
    level = relic["level"]
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
    raw: dict,
    kind: HeroType,
    artifact_ids: list[int],
    relics: tuple[Bonus, ...],
    great_hall: dict[str, tuple[Bonus, ...]],
) -> Champion:
    return Champion(
        id=raw["id"],
        name=kind.name or f"type {raw['type_id']}",
        type_id=raw["type_id"],
        faction=kind.faction,
        element=kind.element,
        role=kind.role,
        rarity=kind.rarity,
        grade=raw["grade"],
        level=raw["level"],
        awakening=raw["awakened_grade"],
        empower=raw["empower"],
        masteries=frozenset(raw["masteries"]),
        artifact_ids=tuple(artifact_ids),
        relics=relics,
        great_hall=great_hall.get(kind.element, ()),
        skill_levels={int(skill_id): level for skill_id, level in raw["skills"].items()},
        marker=raw["marker"],
    )


def parse_artifact(raw: dict) -> Artifact:
    return Artifact(
        id=raw["id"],
        slot=Slot(raw["kind"]),
        set_id=raw["set"],
        rank=raw["rank"],
        rarity=raw["rarity"],
        level=raw["level"],
        primary=parse_line(raw["primary"]),
        substats=tuple(parse_line(sub) for sub in raw["substats"]),
        ascension=parse_line(raw["ascend"]) if raw["ascend"] else None,
        ascend_level=raw["ascend_level"] or 0,
        faction=None if raw["faction"] == NO_FACTION else faction_name(raw["faction"]),
        reworked=bool(raw["rerolls"]),
        variant=raw["variant"],
    )


def parse_line(raw: dict) -> StatLine:
    kind = raw["stat"]
    return StatLine(
        kind=kind,
        stat=STAT_NAMES.get(kind),
        value=raw["value"],
        absolute=raw["absolute"],
        glyph=raw["glyph"],
        rolls=raw["rolls"],
    )


def parse_preset(raw: dict) -> Preset:
    return Preset(raw["id"], raw["name"], raw["area"], team(raw["heroes"]))


def parse_gear_preset(raw: dict) -> GearPreset:
    return GearPreset(raw["id"], raw["name"], raw["accessories"], tuple(raw["artifact_ids"]))


def parse_raid(raw: dict) -> ChimeraRaid:
    start = datetime.fromtimestamp(raw["start"], UTC)
    return ChimeraRaid(start=start, number=raw["number"], prize_offset=raw["prize_offset"])


def team(champion_ids: list[int]) -> tuple[int, ...]:
    """A team's champions, without its empty slots (the game marks them 0 or -1)."""
    return tuple(champion_id for champion_id in champion_ids if champion_id > 0)


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
            debuffs=frozenset(raw["debuffs"]),
            buffs=frozenset(raw["buffs"]),
            effect_kinds=frozenset(raw["effect_kinds"]),
            target_hp_damage=raw["target_hp_damage"],
            cooldown=raw["cooldown"] or 0,
            placements=tuple(
                Placement(
                    kind=p["kind"],
                    status=p["status"],
                    turns=p["turns"],
                    chance=p["chance"],
                    target=p["target"] or "",
                    on_boss=p["on_boss"],
                    unresistable=p["unresistable"],
                )
                for p in raw["placements"]
            ),
            books=tuple(Book(b["type"], b["value"]) for b in raw["books"]),
        )
        for skill_id, raw in read_json(static / "skills.json").items()
    }


@lru_cache(maxsize=2)
def cached_tables(static: Path, schema: Path, league: str, stamp: tuple[int, ...]) -> Tables:
    """`parse_tables`, reparsed only when a game update rewrites the tables (`stamp`, only
    the cache key: `tables_stamp`), not with each snapshot."""
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
        hero_types={t["id"]: parse_hero_type(t) for t in hero_types},
        glyphs=parse_glyphs(read_json(static / "glyphs.json")),
        gear=parse_gear(read_json(static / "gear.json")),
    )


def parse_hero_type(raw: dict) -> HeroType:
    first = raw["forms"][0]
    return HeroType(
        name=raw["name"],
        faction=faction_name(raw["fraction"]),
        rarity=raw["rarity"],
        element=first["element"],
        role=first["role"],
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
