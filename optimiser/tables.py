"""
tables.py - the game's words and fixed tables (`paths.GAME`, from `just static`), parsed once
into the shapes the stat model and solver use: stats, slots and factions by the game's names,
glyphs, gear, sets, skills, champion types, masteries and the Great Hall.

- `Stat`, `STAT_NAMES`, `Stats`, `Bonus`: stats (by the game's names), and the bonuses that
  raise them
- `Slot`, `ARMOUR`: where gear goes
- `GlyphKind`, `GlyphGrade`: glyphs, by the stat they raise and how strong they are
- `GearLine`, `GearTables`: gear stats by level and by ascension level, and the stars each
  slot needs
- `IgnoreDefence`, `DamageBonus`, `FixedSet`, `VariableSet`, `ArtifactSet`: set bonuses by
  piece count
- `Hit`, `Effect`, `Placement`, `Book`, `Skill`: champion skills, as far as damage (and what
  else scales) and what they place and do (how often, how surely, on whom) go
- `HeroForm`, `Aura`, `HeroType`, `LoreOfSteel`, `MasteryType`, `EmpowerSubstitute`, `Tables`:
  the game's fixed tables
- `AFFINITIES`, `GLYPH_RARITIES`, `FACTION_NAMES`, `FACTION_LABELS`, `NO_FACTION`,
  `faction_name`, `faction_label`: what the game's words mean
- `cached_tables` (`tables_stamp`), `parse_tables`: the loader, reparsed only after a game update
- `parse_sets` (`parse_ignore`, `parse_damage`), `parse_skills`, `parse_hero_type`
  (`parse_aura`), `parse_forms`, `parse_glyphs`, `parse_gear` (`by_line`): its steps
- `parse_bonus`, `parse_bonuses`, `parse_levels`, `read_json`: what the steps (and the
  account's) share
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
    bonus at each ascension level (1 first), by rank. Rarity changes neither.
    `required_grade`: the stars a slot needs (`slot_unlocked`); slots absent are always open."""

    max_level: int
    primary: dict[GearLine, dict[int, tuple[float, ...]]]
    ascension: dict[GearLine, dict[int, tuple[float, ...]]]
    required_grade: dict[Slot, int]


@dataclass(frozen=True)
class IgnoreDefence:
    """A set's ignore-DEF passive, as a fraction (0.25 ignores 25 %). Sets granting the same
    skill don't stack unless `per_set` (Cruel); `aoe_only` applies to AoE skills only."""

    skill_id: int
    value: float
    per_set: bool
    aoe_only: bool


@dataclass(frozen=True)
class DamageBonus:
    """A set's extra damage on its wearer's hits, as a fraction (0.12 is +12 %), with the
    wearer at full HP (Zeal's and Fury's scale with it). Sets granting the same skill count
    once unless `per_set` (Zeal), and then at most `cap` in all."""

    skill_id: int
    value: float
    per_set: bool
    cap: float | None


@dataclass(frozen=True)
class FixedSet:
    """A set whose bonus counts once per `pieces` pieces worn."""

    id: int
    name: str
    pieces: int
    bonuses: tuple[Bonus, ...]
    ignore: tuple[IgnoreDefence, ...]
    damage: tuple[DamageBonus, ...]


@dataclass(frozen=True)
class VariableSet:
    """A set whose bonus grows with each piece: the total at each piece count."""

    id: int
    name: str
    totals: dict[int, tuple[Bonus, ...]]
    ignore_at: dict[int, tuple[IgnoreDefence, ...]]  # piece count -> ignore-DEF passives
    damage_at: dict[int, tuple[DamageBonus, ...]]  # piece count -> damage bonuses


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
    always, False never, None when a condition decides), whether it can't be resisted, and
    `repeats`: how many of it the skill places (two Poisons, three hits each placing one). A
    relic's effects may be for one relic skill level (`relic_level`), and may answer a status
    being placed by placing another of it (`echo`: the status)."""

    kind: str
    status: str | None
    turns: int | None
    chance: float | None
    target: str
    on_boss: bool | None
    unresistable: bool
    repeats: int = 1
    relic_level: int | None = None
    echo: str | None = None


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
    description: str = ""  # the game's text, markup stripped

    def damage_bonus_at(self, level: int) -> float:
        """What the books a skill at `level` has had add to its damage."""
        return sum(self.book_damage[: level - 1])

    def chance_bonus_at(self, level: int) -> float:
        """What they add to its effects' chances."""
        return sum(book.value for book in self.books[: level - 1] if book.type == "EffectChance")

    def cooldown_at(self, level: int) -> int:
        """Its cooldown after them, each cooldown book a turn less."""
        taken = self.books[: level - 1]
        turns = sum(round(book.value) for book in taken if book.type == "CooltimeTurn")
        return max(self.cooldown - turns, 0)


@dataclass(frozen=True)
class HeroForm:
    """One of a champion type's forms (mythicals have two): its role as the game names it
    (Attack, Defense, Health, Support), its skills, and its base stats as the static data
    holds them (HP / 15, crit in %; `levels` scales them)."""

    role: str
    skills: tuple[int, ...]
    unscaled: Stats


@dataclass(frozen=True)
class Aura:
    """A leader skill: a bonus for the team in battles of one `area` (the game's: Arena,
    Dungeon, Fractions, DoomTower, Story; None: any), held to allies of one affinity, faction
    or rarity where those are set."""

    bonus: Bonus
    area: str | None
    element: str | None
    faction: str | None  # `faction_name`
    rarity: str | None


@dataclass(frozen=True)
class HeroType:
    """A champion type's fixed facts, by the game's names but for the faction (its display
    name, `faction_name`); affinity and role are its first form's (a form never changes
    affinity). Mythicals have an aura per form."""

    name: str
    faction: str
    rarity: str
    element: str
    role: str
    auras: tuple[Aura, ...] = ()


@dataclass(frozen=True)
class MasteryType:
    """A mastery's place in its tree, 1 (the top) to 6 (Helmsmasher's), and its price in scrolls:
    the game's `MasteryPointType` (Bronze, Silver, Gold) -> how many."""

    row: int
    price: Mapping[str, int]


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
    mastery_types: dict[int, MasteryType]
    lore_of_steel: LoreOfSteel
    sets: dict[int, ArtifactSet]
    skills: dict[int, Skill]
    hero_forms: dict[int, tuple[HeroForm, ...]]  # hero type id -> every form, first first
    hero_types: dict[int, HeroType]
    glyphs: dict[GlyphKind, dict[GlyphGrade, float]]  # each grade's top roll, weakest first
    gear: GearTables


AFFINITIES = ("Magic", "Force", "Spirit", "Void")


GLYPH_RARITIES = ("Uncommon", "Rare", "Epic", "Legendary")


# The factions the game shows under another name than its own (the art is named by these)
# A faction's key: the game's internal name, but for the renamed (the game's tables, stage
# conditions and Faction Wars crypts still say Samurai and Olympians). Champions, pieces,
# relics and asset files go by the key; `faction_label` is what's shown.
FACTION_NAMES = {"Samurai": "Shadowkin", "Olympians": "Argonites"}


FACTION_LABELS = {
    "BannerLords": "Banner Lords",
    "CovenOfMagi": "Coven of Magi",
    "DarkElves": "Dark Elves",
    "HighElves": "High Elves",
    "KnightsRevenant": "Knights Revenant",
    "LizardMen": "Lizardmen",
    "OgrynTribes": "Ogryn Tribes",
    "SacredOrder": "Sacred Order",
    "SylvanWatchers": "Sylvan Watchers",
    "UndeadHordes": "Undead Hordes",
}


NO_FACTION = "Unknown"  # a piece any faction can wear


def faction_name(game_name: str) -> str:
    """The faction's key, from any of the game's names for it."""
    return FACTION_NAMES.get(game_name, game_name)


def faction_label(name: str) -> str:
    """The faction as the game shows it: "Dark Elves"."""
    key = faction_name(name)
    return FACTION_LABELS.get(key, key)


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
        damage = {tier["pieces"]: parse_damage(tier["damage_bonus"]) for tier in raw["tiers"]}

        if raw["variable"]:
            sets[set_id] = VariableSet(set_id, raw["name"], totals, ignore, damage)
        else:
            pieces = raw["pieces"]
            sets[set_id] = FixedSet(
                set_id, raw["name"], pieces, totals[pieces], ignore[pieces], damage[pieces]
            )

    return sets


def parse_ignore(raw: list[dict]) -> tuple[IgnoreDefence, ...]:
    return tuple(IgnoreDefence(i["skill"], i["value"], i["per_set"], i["aoe_only"]) for i in raw)


def parse_damage(raw: list[dict]) -> tuple[DamageBonus, ...]:
    return tuple(DamageBonus(d["skill"], d["value"], d["per_set"], d["cap"]) for d in raw)


def parse_skills(static: Path) -> dict[int, Skill]:
    return {
        int(skill_id): Skill(
            id=int(skill_id),
            name=raw["name"] or f"skill {skill_id}",
            description=raw.get("description", ""),
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
                    repeats=p.get("repeats", 1),
                    relic_level=p.get("relic_level"),
                    echo=p.get("echo"),
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
        mastery_types={
            int(mastery_id): MasteryType(m["row"], m["price"])
            for mastery_id, m in bonuses["mastery_types"].items()
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
        auras=tuple(parse_aura(aura) for aura in raw.get("auras", ())),
    )


def parse_aura(raw: dict) -> Aura:
    return Aura(
        bonus=Bonus(STAT_NAMES[raw["stat"]], raw["value"], raw["absolute"]),
        area=raw["area"],
        element=raw["element"],
        faction=faction_name(raw["faction"]) if raw["faction"] else None,
        rarity=raw["rarity"],
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
        required_grade={Slot(kind): grade for kind, grade in raw["required_grade"].items()},
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
