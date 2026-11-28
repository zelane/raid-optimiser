"""
targets.py - the target picker: an enemy to aim damage at, picked by zone (Dungeons, Clan
Boss, Faction Wars…), group (a dungeon, a crypt), difficulty and stage, then one enemy of the
stage's waves (the last unless picked), shown with its portrait and stats as the battle
starts. A component: any page can show it, and the page decides what the pick fills in (the
champion page: the DEF damage is ranked against; the team finder: what the stage asks of a
team).

- `ZONES`, `ZONE_NAMES`, `REGION_NAMES`, `LEFT_OUT_REGIONS`, `PLACEHOLDER_NAME`,
  `SHOWN_STATS`: what the picker offers and what it calls things
- `StageChoice`, `Difficulty`, `Group`, `Zone`: the catalogue
- `Option`, `StatText`, `EnemyCard`, `TargetPicker`: the views
- `target_picker`: the picker for a query (the component's one entry point)
- `catalogue`, `area_zone`, `clan_boss_zone`, `chimera_zone`, `rotation_label`,
  `group_labels`, `common_words`, `difficulty_label`, `split_words`: the catalogue's pieces
- `locate`, `choose`, `options`, `enemy_cards`, `enemy_card`, `default_enemy`, `target_key`:
  the picker's pieces
"""

import re
from collections import Counter
from dataclasses import dataclass

from optimiser.enemies import Area, Enemies, Placement, Stage, enemy_stats, is_boss
from optimiser.labels import STAT_LABELS, format_stat
from optimiser.tables import Stat
from webui.forms.targets import TargetQuery
from webui.service.views import asset_url

# The areas whose enemies are worth aiming at, in the picker's order, and their names where
# the game's are internal ones.
ZONES = (
    "Dungeon",
    "AllianceBoss",
    "Chimera",
    "Fractions",
    "Hydra",
    "DoomTower",
    "FoggyForest",
    "CursedCity",
    "CooperationEventWorldBoss",
    "Story",
)
ZONE_NAMES = {
    "AllianceBoss": "Clan Boss",
    "CooperationEventWorldBoss": "Demon Lord (co-op)",
    "CursedCity": "Cursed City",
}
REGION_NAMES = {"CooperationEventWorldBoss": "Tainted Demon Lord"}
LEFT_OUT_REGIONS = {"EventDungeon"}  # its stages change with each event
PLACEHOLDER_NAME = re.compile(r"Hero \d+ name")  # minions the game never names
SHOWN_STATS = (Stat.HP, Stat.ATK, Stat.DEF, Stat.SPD, Stat.RES, Stat.ACC)


@dataclass(frozen=True)
class StageChoice:
    id: int
    label: str


@dataclass(frozen=True)
class Difficulty:
    key: str
    label: str
    stages: tuple[StageChoice, ...]  # never empty


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    difficulties: tuple[Difficulty, ...]  # never empty


@dataclass(frozen=True)
class Zone:
    key: str
    label: str
    groups: tuple[Group, ...]  # never empty


@dataclass(frozen=True)
class Option:
    value: str
    label: str
    selected: bool


@dataclass(frozen=True)
class StatText:
    label: str
    text: str


@dataclass(frozen=True)
class EnemyCard:
    """An enemy of the wave shown, drawn as a champion's tile (no level or stars)."""

    key: str  # "<wave>-<slot>"
    name: str
    portrait_url: str | None
    affinity: str
    affinity_icon_url: str | None
    boss: bool
    picked: bool
    stats: tuple[StatText, ...]
    defence: int
    resistance: int = 0
    speed: int = 0
    accuracy: int = 0
    rarity: str = "Common"  # the tile's frame


@dataclass(frozen=True)
class TargetPicker:
    """`target` ("<stage>:<wave>:<slot>") names the pick, for a form to keep; `stage` is its
    stage's id."""

    zones: tuple[Option, ...]
    groups: tuple[Option, ...]
    difficulties: tuple[Option, ...]
    stages: tuple[Option, ...]
    waves: tuple[Option, ...]  # one: nothing to pick
    title: str
    enemies: tuple[EnemyCard, ...]
    picked: EnemyCard
    target: str
    stage: int


def target_picker(enemies: Enemies, query: TargetQuery) -> TargetPicker:
    zones = catalogue(enemies)

    # 1. Where the query points: a saved target, or each level's pick (one changed: the
    # levels under it go back to their defaults).
    zone, group, difficulty, stage_choice = locate(zones, query)
    stage = enemies.stages[stage_choice.id]

    # 2. The wave (the last unless asked), and which of its enemies is picked.
    waves = sorted({p.wave for p in stage.formations[0]})
    wave = query.wave if query.wave in waves else waves[-1]
    cards = enemy_cards(enemies, stage, wave, query.enemy)
    picked = next(card for card in cards if card.picked)

    return TargetPicker(
        zones=options(zones, zone),
        groups=options(zone.groups, group),
        difficulties=options(group.difficulties, difficulty),
        stages=tuple(Option(str(s.id), s.label, s is stage_choice) for s in difficulty.stages),
        waves=tuple(Option(str(w), f"Wave {w}", w == wave) for w in waves),
        title=f"{group.label} · {difficulty.label} · {stage_choice.label}",
        enemies=cards,
        picked=picked,
        target=f"{stage.id}:{picked.key.replace('-', ':')}",
        stage=stage.id,
    )


def catalogue(enemies: Enemies) -> tuple[Zone, ...]:
    by_id = {area.id: area for area in enemies.areas}
    zones = []

    for key in ZONES:
        if key == "AllianceBoss":
            zones.append(clan_boss_zone(enemies))
        elif key == "Chimera":
            zones.append(chimera_zone(enemies))
        elif (area := by_id.get(key)) and (zone := area_zone(area, enemies)):
            zones.append(zone)

    return tuple(zones)


def area_zone(area: Area, enemies: Enemies) -> Zone | None:
    regions = [r for r in area.regions if r.id not in LEFT_OUT_REGIONS]
    labels = group_labels([(r.id, REGION_NAMES.get(r.id, r.name)) for r in regions])
    groups = []

    for region in regions:
        difficulties = tuple(
            Difficulty(
                key,
                difficulty_label(key),
                tuple(
                    StageChoice(stage_id, f"Stage {number}")
                    for number, stage_id in enumerate(ids, 1)
                    if stage_id in enemies.stages
                ),
            )
            for key, ids in region.stages.items()
        )

        if difficulties := tuple(d for d in difficulties if d.stages):
            groups.append(Group(region.id, labels[region.id], difficulties))

    if not groups:
        return None

    return Zone(area.id, ZONE_NAMES.get(area.id, area.name), tuple(groups))


def clan_boss_zone(enemies: Enemies) -> Zone:
    """The clan boss's stages are its tiers × affinities, which its area doesn't say."""
    difficulties = tuple(
        Difficulty(
            tier.difficulty,
            difficulty_label(tier.difficulty),
            tuple(StageChoice(stage_id, affinity) for affinity, stage_id in tier.stages.items()),
        )
        for tier in enemies.clan_boss
    )
    return Zone(
        "AllianceBoss",
        ZONE_NAMES["AllianceBoss"],
        (Group("DemonLord", "Demon Lord", difficulties),),
    )


def chimera_zone(enemies: Enemies) -> Zone:
    """The Chimera's stages are its tiers × its four rotations (the forms' affinities), which
    its area (a region per rotation) doesn't line up by tier."""
    difficulties = tuple(
        Difficulty(
            tier.difficulty,
            difficulty_label(tier.difficulty),
            tuple(
                StageChoice(stage_id, rotation_label(enemies, stage_id)) for stage_id in tier.stages
            ),
        )
        for tier in enemies.chimera.tiers
    )
    return Zone("Chimera", "Chimera", (Group("Chimera", "Chimera", difficulties),))


def rotation_label(enemies: Enemies, stage_id: int) -> str:
    """A rotation by its forms' affinities: "Force, Ultimate Void" (the animal forms share
    one)."""
    placement = enemies.stages[stage_id].formations[0][0]
    ultimate, animal, *_ = enemies.types[placement.type_id].forms
    return f"{animal.affinity}, Ultimate {ultimate.affinity}"


def group_labels(regions: list[tuple[str, str]]) -> dict[str, str]:
    """Each region's name; where several share one (the four Iron Twins fortresses, Hydra's
    rotations, Grim Forest's zones), the words of its id the others don't share go after it:
    "Iron Twins Fortress: Void", "Grim Forest: Extra Hard", "Hydra: Season 3"."""
    shared = Counter(name for _, name in regions)
    labels = {}

    for region_id, name in regions:
        if shared[name] == 1:
            labels[region_id] = name
            continue

        siblings = [
            split_words(other).split() for other, other_name in regions if other_name == name
        ]
        own = split_words(region_id).split()
        start, end = common_words(siblings)
        distinct = own[start : len(own) - end]

        if distinct and distinct[0].isdigit() and start:
            distinct = [own[start - 1], *distinct]  # "Season 3", not "3"

        labels[region_id] = f"{name}: {' '.join(distinct)}" if distinct else name

    return labels


def common_words(names: list[list[str]]) -> tuple[int, int]:
    """How many words every name starts with alike, and how many it ends with alike."""
    shortest = min(len(words) for words in names)
    start = 0

    while start < shortest and len({words[start] for words in names}) == 1:
        start += 1

    end = 0

    while start + end < shortest and len({words[-1 - end] for words in names}) == 1:
        end += 1

    return start, end


def difficulty_label(key: str) -> str:
    return (
        "Normal"
        if key == "None"
        else split_words(key).replace("Ultra Nightmare", "Ultra-Nightmare")
    )


def split_words(name: str) -> str:
    """ "ForceDoubleAscendDungeon" -> "Force Double Ascend Dungeon"; digits are words too."""
    return " ".join(re.findall(r"[A-Z][a-z]*|[a-z]+|\d+", name))


def locate(
    zones: tuple[Zone, ...], query: TargetQuery
) -> tuple[Zone, Group, Difficulty, StageChoice]:
    if query.target is not None:
        for zone in zones:
            for group in zone.groups:
                for difficulty in group.difficulties:
                    for stage in difficulty.stages:
                        if stage.id == query.target.stage:
                            return zone, group, difficulty, stage

    zone = choose(zones, query.zone, default=0)
    group = choose(zone.groups, query.group, default=0)
    difficulty = choose(group.difficulties, query.difficulty, default=-1)
    by_id = {str(s.id): s for s in difficulty.stages}
    stage = by_id.get(query.stage or "") or difficulty.stages[-1]
    return zone, group, difficulty, stage


def choose[T: (Zone, Group, Difficulty)](items: tuple[T, ...], key: str | None, default: int) -> T:
    """The item with the key asked, else the default: the first, or the last (the hardest)."""
    return next((item for item in items if item.key == key), items[default])


def options(
    items: tuple[Zone, ...] | tuple[Group, ...] | tuple[Difficulty, ...], picked
) -> tuple[Option, ...]:
    return tuple(Option(item.key, item.label, item is picked) for item in items)


def enemy_cards(
    enemies: Enemies, stage: Stage, wave_number: int, asked: str | None
) -> tuple[EnemyCard, ...]:
    """The wave's enemies, bosses first; the one asked for is picked, else the main one."""
    formation = stage.formations[0]
    wave = sorted(
        (p for p in formation if p.wave == wave_number),
        key=lambda p: (not is_boss(p, enemies.types[p.type_id]), p.slot),
    )
    keys = [target_key(p) for p in wave]
    picked = asked if asked in keys else default_enemy(enemies, stage, wave)
    return tuple(enemy_card(enemies, stage, p, picked) for p in wave)


def enemy_card(enemies: Enemies, stage: Stage, placement: Placement, picked: str) -> EnemyCard:
    enemy = enemies.types[placement.type_id]
    stats = enemy_stats(stage, placement, enemy)
    affinity = enemy.forms[0].affinity
    return EnemyCard(
        key=target_key(placement),
        name="Minion" if PLACEHOLDER_NAME.fullmatch(enemy.name) else enemy.name,
        portrait_url=asset_url("portraits", str(enemy.id))
        or asset_url("portraits", str(enemy.id // 10 * 10)),
        affinity=affinity,
        affinity_icon_url=asset_url("affinities", affinity.lower()),
        boss=is_boss(placement, enemy),
        picked=target_key(placement) == picked,
        stats=tuple(
            StatText(STAT_LABELS[stat], format_stat(stat, stats[stat])) for stat in SHOWN_STATS
        ),
        defence=round(stats[Stat.DEF]),
        resistance=round(stats[Stat.RES]),
        speed=round(stats[Stat.SPD]),
        accuracy=round(stats[Stat.ACC]),
    )


def default_enemy(enemies: Enemies, stage: Stage, wave: list[Placement]) -> str:
    """The boss, else the toughest (most HP) of the wave."""
    if bosses := [p for p in wave if is_boss(p, enemies.types[p.type_id])]:
        return target_key(bosses[0])

    toughest = max(wave, key=lambda p: enemy_stats(stage, p, enemies.types[p.type_id])[Stat.HP])
    return target_key(toughest)


def target_key(placement: Placement) -> str:
    return f"{placement.wave}-{placement.slot}"
