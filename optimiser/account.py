"""
account.py - the account (the memory reader's snapshot, `paths.SNAPSHOT`), parsed once at the
boundary into the shapes the stat model and solver use, over the game's tables (`tables`).

- `StatLine`, `Artifact`, `Champion`, `slot_unlocked`: what can be worn, by whom, and in
  which slots
- `LOCK_LEVELS`, `Locks`: champion locks, which keep gear on its champion
- `Relic`: a relic the account has
- `SkillSettings`, `Preset`, `GearPreset`, `ChimeraRaid`, `StageProgress`: saved teams (and
  how auto plays each champion in them), global gear presets, the Chimera's current raid, and
  progress on a stage
- `Account`: everything a solve needs, and the account's saved teams (`preset`: one by id)
- `DEFAULT_LEAGUE`: the arena league when the game doesn't say
- `load_account`: the loader
- `worn_gear`: what a champion wears
- `great_hall_by_affinity`, `parse_relics` (`relic_stats`), `parse_champion`, `parse_artifact`
  (`parse_line`), `parse_preset` (`parse_skill_settings`, `parse_sequence`), `parse_gear_preset`,
  `parse_raid`, `team`: its steps
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from optimiser.tables import (
    AFFINITIES,
    NO_FACTION,
    STAT_NAMES,
    Aura,
    Bonus,
    GearTables,
    HeroForm,
    HeroType,
    Slot,
    Stat,
    Tables,
    cached_tables,
    faction_name,
    parse_bonus,
    read_json,
    tables_stamp,
)


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
    # Unspent mastery scrolls: the game's `MasteryPointType` (Bronze, Silver, Gold: Basic,
    # Advanced, Divine) -> how many; empty in snapshots from before the reader read them.
    scrolls: Mapping[str, int] = field(default_factory=dict)
    marker: str = "None"  # its tag in game (`HeroMarker`: Favorite, ArenaFirst, …), at most one
    # Which of its forms (`Tables.hero_forms`) it's taken in, 0 first: mythicals have two, and
    # each has its own base stats and skills. A playable form never changes affinity, so the
    # Great Hall doesn't depend on it. The game doesn't say; a request does.
    form: int = 0

    @property
    def ascension(self) -> int:
        """0 to 6: the type id's last digit (each ascension is a type of its own)."""
        return self.type_id % 10

    def form_in(self, tables: Tables) -> HeroForm:
        """The form they're in (`form`), in the game's tables."""
        return tables.hero_forms[self.type_id][self.form]

    def reached_by(self, aura: Aura) -> bool:
        """Whether a leader's aura reaches them: their affinity, faction and rarity."""
        held = [
            (aura.element, self.element),
            (aura.faction, self.faction),
            (aura.rarity, self.rarity),
        ]
        return all(wanted in (None, theirs) for wanted, theirs in held)

    def skills_in(self, tables: Tables) -> tuple[int, ...]:
        """Their skill ids, in the form they're in; none if the type is unknown."""
        forms = tables.hero_forms.get(self.type_id, ())
        return forms[self.form].skills if self.form < len(forms) else ()


LOCK_LEVELS = range(1, 6)  # 5 the strongest


# Champion id -> lock level. A lock keeps a champion's gear out of solves that only allow gear
# from champions locked below some level; unlocked champions are absent (0).
type Locks = Mapping[int, int]


@dataclass(frozen=True)
class SkillSettings:
    """A champion's skill settings for one wave of a saved team, as auto plays them:
    `priorities` by skill id, the game's `SkillPriorityType` names (Default, First, Second,
    Third, NotUsed), and the skills it opens with (`openers`, in order)."""

    priorities: Mapping[int, str]
    openers: tuple[int, ...] = ()


@dataclass(frozen=True)
class Preset:
    """A saved team: `area` is the game's preset type (Pvp for arena attack, Chimera, Hydra,
    DoomTower, …); `skill_settings` by champion id, one per wave (the game's sequences; empty
    in snapshots from before the reader read them)."""

    id: int
    name: str
    area: str
    champion_ids: tuple[int, ...]
    skill_settings: Mapping[int, tuple[SkillSettings, ...]] = field(default_factory=dict)


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
class StageProgress:
    """How far the account has got on a stage it has fought: the game counts its stars
    (battle quests done), not which ones."""

    passed: bool
    stars: int


def slot_unlocked(champion: Champion, slot: Slot, gear: GearTables) -> bool:
    """Whether the champion can wear gear in the slot. The game's table gives the stars each
    accessory slot needs (Ring 4, Amulet 5, Banner 6); the Amulet and Banner also need them
    ascended (no rank 5 below ascension 5 wears an amulet, though they wear rings), the Ring
    only the rank (rank 4s at ascension 0 wear rings)."""
    if (required := gear.required_grade.get(slot)) is None:
        return True

    if champion.grade < required:
        return False

    return slot == Slot.RING or champion.ascension >= required


@dataclass(frozen=True)
class Relic:
    """A relic the account has: its type, rank and level."""

    id: int
    type_id: int
    rank: int
    level: int


@dataclass(frozen=True)
class Account:
    """`mailbox`: gear that overflowed the inventory, waiting in the mailbox to be claimed;
    `relic_types`: the relic types the account has (worn or not), `relic_items` each relic,
    `worn_relics` who wears which (champion id -> relic ids); `presets`, the arena
    defenses (classic, and 3v3's three teams), `gear_presets` (the global ones; champions' own
    presets are left out), `chimera_raid` and `stages` (progress on the stages fought): what
    the game holds besides gear."""

    user_id: int  # the Raid account
    champions: dict[int, Champion]
    artifacts: tuple[Artifact, ...]
    owners: dict[int, int]  # artifact id -> id of the champion wearing it
    tables: Tables
    mailbox: tuple[Artifact, ...] = ()
    relic_types: frozenset[int] = frozenset()
    relic_items: dict[int, Relic] = field(default_factory=dict)
    worn_relics: dict[int, tuple[int, ...]] = field(default_factory=dict)
    presets: tuple[Preset, ...] = ()
    arena_defense: tuple[int, ...] = ()
    arena3x3_defense: tuple[tuple[int, ...], ...] = ()
    gear_presets: tuple[GearPreset, ...] = ()
    chimera_raid: ChimeraRaid | None = None
    stages: dict[int, StageProgress] = field(default_factory=dict)

    def preset(self, preset_id: int) -> Preset | None:
        """The saved team with this id; None once it's gone."""
        return next((preset for preset in self.presets if preset.id == preset_id), None)


DEFAULT_LEAGUE = "GoldV"  # if the game doesn't say


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
        relic_items={
            r["id"]: Relic(r["id"], r["type_id"], r["rank"], r["level"]) for r in account["relics"]
        },
        worn_relics={int(hero): tuple(ids) for hero, ids in account["worn_relics"].items() if ids},
        presets=tuple(parse_preset(raw) for raw in account["presets"]),
        arena_defense=team(account["arena_defense"]),
        arena3x3_defense=tuple(team(raw) for raw in account["arena3x3_defense"]),
        gear_presets=tuple(
            parse_gear_preset(raw) for raw in account["gear_presets"] if raw["hero_id"] is None
        ),
        chimera_raid=parse_raid(account["chimera"]) if account["chimera"] else None,
        stages={
            int(stage_id): StageProgress(raw["passed"], raw["stars"])
            for stage_id, raw in account.get("stages", {}).items()
        },
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
        scrolls={kind: count for kind, count in raw.get("scrolls", {}).items() if count},
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
    settings = {
        setup["hero_id"]: parse_skill_settings(setup) for setup in raw.get("priorities", ())
    }
    return Preset(raw["id"], raw["name"], raw["area"], team(raw["heroes"]), settings)


def parse_skill_settings(setup: dict) -> tuple[SkillSettings, ...]:
    """One per wave; a record from before the game kept sequences is one."""
    return tuple(parse_sequence(sequence) for sequence in setup["sequences"] or [setup])


def parse_sequence(sequence: dict) -> SkillSettings:
    openers = sequence.get("starters") or ([sequence["starter"]] if sequence.get("starter") else [])
    return SkillSettings(
        priorities={int(skill_id): name for skill_id, name in sequence["priorities"].items()},
        openers=tuple(openers),
    )


def parse_gear_preset(raw: dict) -> GearPreset:
    return GearPreset(raw["id"], raw["name"], raw["accessories"], tuple(raw["artifact_ids"]))


def parse_raid(raw: dict) -> ChimeraRaid:
    start = datetime.fromtimestamp(raw["start"], UTC)
    return ChimeraRaid(start=start, number=raw["number"], prize_offset=raw["prize_offset"])


def team(champion_ids: list[int]) -> tuple[int, ...]:
    """A team's champions, without its empty slots (the game marks them 0 or -1)."""
    return tuple(champion_id for champion_id in champion_ids if champion_id > 0)
