"""
enemies.py - the game's enemies (`enemies.json`, base stats from `hero_types.json`): each
stage's teams, the restrictions on the player's team, and the enemies' stats as a battle
starts: base at their rank and level (`levels`), then the stage's and the slot's modifiers.
The boss modes' own tables come with them: the clan boss's difficulties, the Chimera's forms
and trials, and the areas' shield caps.

- `Modifier`, `Restriction`, `Placement`, `Stage`, `EnemyType`, `Skill`: stages and who's in them
- `ClanBossTier`, `Trial`, `ChimeraTier`, `Chimera`: the boss modes' tables
- `Enemies`: all of it
- `CHIMERA_FORMS`: the Chimera's forms, in its type's order
- `load_enemies`: the loader
- `enemy_stats`: an enemy's stats in a stage
- `modifier_applies`, `is_boss`: what the stats depend on
- `parse_stage`, `parse_placement`, `parse_modifier`, `parse_restriction`, `parse_type`,
  `parse_skill`, `parse_chimera`, `parse_trial`: the loader's steps
"""

from dataclasses import dataclass
from pathlib import Path

from optimiser.account import STAT_NAMES, Stat, Stats, read_json
from optimiser.levels import base_stats

# By their skills (Almighty Chimera, Ram, Lion, Viper); the trials and sequence name them so.
CHIMERA_FORMS = ("Ultimate", "Ram", "Lion", "Snake")


@dataclass(frozen=True)
class Modifier:
    """A change to enemies' stats in one wave: a fraction of the base stat (`absolute`
    False: −0.9 is −90%) or a flat amount; `boss_only`: the bosses' alone."""

    wave: int
    stat: Stat
    value: float
    absolute: bool
    boss_only: bool


@dataclass(frozen=True)
class Restriction:
    """Which champions a stage admits: every one on the team must match each listed field
    (an empty tuple admits any)."""

    factions: tuple[str, ...]
    roles: tuple[str, ...]
    rarities: tuple[str, ...]
    affinities: tuple[str, ...]


@dataclass(frozen=True)
class Placement:
    """An enemy in a stage: its type, wave and slot, rank and level, and its own modifiers."""

    type_id: int
    wave: int
    slot: int
    grade: int
    level: int
    boss: bool
    modifiers: tuple[Modifier, ...]


@dataclass(frozen=True)
class Stage:
    """A stage: where it is, the team it takes, and the enemies it fields (each formation is
    one possible line-up, all waves)."""

    id: int
    area: str | None
    region: str | None
    difficulty: str | None
    team_size: int
    restrictions: tuple[Restriction, ...]
    modifiers: tuple[Modifier, ...]
    formations: tuple[tuple[Placement, ...], ...]


@dataclass(frozen=True)
class EnemyForm:
    """One of a type's forms (the Chimera has four): affinity, skills, unscaled base stats."""

    affinity: str
    skills: tuple[int, ...]
    unscaled: Stats


@dataclass(frozen=True)
class EnemyType:
    """A hero type as an enemy; `boss_kind` is the game's boss kind (DemonLord, Chimera, …)."""

    id: int
    name: str
    forms: tuple[EnemyForm, ...]
    boss_kind: str | None
    unkillable: bool


@dataclass(frozen=True)
class Skill:
    """An enemy skill: its text, and its effects as the static data holds them."""

    name: str
    cooldown: int
    description: str
    effects: tuple[dict, ...]


@dataclass(frozen=True)
class ClanBossTier:
    difficulty: str
    health: int
    stages: dict[str, int]  # affinity -> stage id


@dataclass(frozen=True)
class Trial:
    """A Chimera trial: the form and part it belongs to, its level (Easy, Normal, Hard),
    what it asks, and its target (damage, or a count). `counter_limit` is the game's turn
    counter limit, one above the turns the text gives; `requires`: the trial done first;
    `rules`: the game's conditions on what counts toward it."""

    skill: int
    form: str
    part: str
    level: str
    description: str
    target: float
    damage: bool
    counter_limit: int | None
    requires: int | None
    rules: tuple[str, ...]  # its hidden skill's conditions: what counts toward it
    statuses: tuple[str, ...]  # the status effects the game lists for it


@dataclass(frozen=True)
class ChimeraTier:
    difficulty: str
    health: int
    stages: tuple[int, ...]  # one per rotation
    trials: tuple[Trial, ...]


@dataclass(frozen=True)
class Chimera:
    """The Chimera: its form by turn (a form holds until its turn number, then the next one
    takes over), and its difficulties."""

    forms_by_turn: dict[int, str]
    turns_between_forms: int
    tiers: tuple[ChimeraTier, ...]


@dataclass(frozen=True)
class Enemies:
    stages: dict[int, Stage]
    types: dict[int, EnemyType]
    skills: dict[int, Skill]
    shield_caps: dict[str, float]  # area -> the most one shield can hold
    clan_boss: tuple[ClanBossTier, ...]
    chimera: Chimera

    def area_stages(self, area: str) -> list[Stage]:
        return [stage for stage in self.stages.values() if stage.area == area]


def load_enemies(static: Path) -> Enemies:
    raw = read_json(static / "enemies.json")
    stages = {int(k): parse_stage(int(k), v) for k, v in raw["stages"].items()}
    used = {p.type_id for stage in stages.values() for line in stage.formations for p in line}
    bosses = raw["bosses"]
    types = {
        t["id"]: parse_type(t, bosses.get(str(t["id"])))
        for t in read_json(static / "hero_types.json")
        if t["id"] in used
    }
    clan_boss = tuple(
        ClanBossTier(b["difficulty"], b["health"], b["stages"]) for b in raw["clan_boss"]
    )
    return Enemies(
        stages=stages,
        types=types,
        skills={int(k): parse_skill(v) for k, v in raw["skills"].items()},
        shield_caps=raw["shield_caps"],
        clan_boss=clan_boss,
        chimera=parse_chimera(raw["chimera"]),
    )


def enemy_stats(stage: Stage, placement: Placement, enemy: EnemyType, form: int = 0) -> Stats:
    """The enemy's stats as the battle starts: base at its rank and level, plus the stage's
    and the slot's modifiers for its wave. Passives that change stats in battle aren't in."""
    base = base_stats(enemy.forms[form].unscaled, placement.grade, placement.level)
    stats = dict(base)

    for modifier in stage.modifiers + placement.modifiers:
        if not modifier_applies(modifier, placement, enemy):
            continue

        change = modifier.value if modifier.absolute else base[modifier.stat] * modifier.value
        stats[modifier.stat] += change

    return stats


def modifier_applies(modifier: Modifier, placement: Placement, enemy: EnemyType) -> bool:
    return modifier.wave == placement.wave and (not modifier.boss_only or is_boss(placement, enemy))


def is_boss(placement: Placement, enemy: EnemyType) -> bool:
    return placement.boss or enemy.boss_kind is not None


def parse_stage(stage_id: int, raw: dict) -> Stage:
    return Stage(
        id=stage_id,
        area=raw["area"],
        region=raw["region"],
        difficulty=raw["difficulty"],
        team_size=raw["team_size"],
        restrictions=tuple(parse_restriction(c) for c in raw["conditions"]),
        modifiers=parse_modifiers(raw["modifiers"]),
        formations=tuple(tuple(parse_placement(p) for p in line) for line in raw["formations"]),
    )


def parse_placement(raw: dict) -> Placement:
    return Placement(
        type_id=raw["type"],
        wave=raw["wave"],
        slot=raw["slot"],
        grade=raw["grade"],
        level=raw["level"],
        boss=raw["boss"],
        modifiers=parse_modifiers(raw["modifiers"]),
    )


def parse_modifiers(raw: list[dict]) -> tuple[Modifier, ...]:
    """The modifiers on stats the model knows (C.HEAL and ignore DEF are left out)."""
    return tuple(parse_modifier(m) for m in raw if m["stat"] in STAT_NAMES)


def parse_modifier(raw: dict) -> Modifier:
    return Modifier(
        wave=raw["wave"],
        stat=STAT_NAMES[raw["stat"]],
        value=raw["value"],
        absolute=raw["absolute"],
        boss_only=raw["boss_only"],
    )


def parse_restriction(raw: dict) -> Restriction:
    return Restriction(
        factions=tuple(raw["factions"] or ()),
        roles=tuple(raw["roles"] or ()),
        rarities=tuple(raw["rarities"] or ()),
        affinities=tuple(raw["affinities"] or ()),
    )


def parse_type(raw: dict, boss: dict | None) -> EnemyType:
    forms = tuple(
        EnemyForm(
            affinity=form["element"],
            skills=tuple(form["skills"]),
            unscaled={STAT_NAMES[k]: v for k, v in form["base_stats"].items() if k in STAT_NAMES},
        )
        for form in raw["forms"]
    )
    return EnemyType(
        id=raw["id"],
        name=raw["name"],
        forms=forms,
        boss_kind=boss["kind"] if boss else None,
        unkillable=bool(boss and boss["unkillable"]),
    )


def parse_skill(raw: dict) -> Skill:
    return Skill(
        name=raw["name"],
        cooldown=raw["cooldown"] or 0,
        description=raw["description"],
        effects=tuple(raw["effects"]),
    )


def parse_chimera(raw: dict) -> Chimera:
    tiers = tuple(
        ChimeraTier(
            difficulty=tier["difficulty"],
            health=tier["health"],
            stages=tuple(tier["stages"]),
            trials=tuple(parse_trial(t) for t in tier["trials"]),
        )
        for tier in raw["tiers"]
    )
    return Chimera(
        forms_by_turn={int(turn): form for turn, form in raw["forms"].items()},
        turns_between_forms=raw["turns_between_forms"],
        tiers=tiers,
    )


def parse_trial(raw: dict) -> Trial:
    return Trial(
        skill=raw["skill"],
        form=raw["form"],
        part=raw["part"],
        level=raw["level"],
        description=raw["description"],
        target=raw["target"],
        damage=raw["damage"],
        counter_limit=raw["counter_limit"],
        requires=raw["requires"],
        rules=tuple(raw["rules"]),
        statuses=tuple(raw["statuses"] or ()),
    )
