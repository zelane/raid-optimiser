"""
enemy_report.py - the enemy store (`enemies`) in the terminal: an area's stages or one stage
(restrictions, enemies and their starting stats, skills), and the Chimera's trials.

    uv run python -m optimiser.enemy_report areas
    uv run python -m optimiser.enemy_report area CooperationEventWorldBoss
    uv run python -m optimiser.enemy_report stage 15019004 --skills
    uv run python -m optimiser.enemy_report chimera --difficulty UltraNightmare

- `main`: the commands
- `print_stage`, `print_enemy`, `print_chimera`: what they print
- `describe_restriction`, `format_stats`: their pieces
"""

import argparse

from optimiser.account import Stat
from optimiser.enemies import CHIMERA_FORMS, Enemies, Restriction, Stage, enemy_stats, load_enemies
from optimiser.paths import GAME

SHOWN_STATS = (Stat.HP, Stat.ATK, Stat.DEF, Stat.SPD, Stat.RES, Stat.ACC, Stat.CR, Stat.CD)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("areas", help="the areas and how many stages each has")
    area = commands.add_parser("area", help="an area's stages")
    area.add_argument("area")
    area.add_argument("--skills", action="store_true")
    stage = commands.add_parser("stage", help="one stage")
    stage.add_argument("stage", type=int)
    stage.add_argument("--skills", action="store_true")
    chimera = commands.add_parser("chimera", help="the Chimera's forms and trials")
    chimera.add_argument("--difficulty", default="UltraNightmare")
    args = parser.parse_args()

    enemies = load_enemies(GAME)

    match args.command:
        case "areas":
            areas = sorted({s.area for s in enemies.stages.values() if s.area})
            for name in areas:
                print(f"{name:28} {len(enemies.area_stages(name)):4} stages")

        case "area":
            for found in enemies.area_stages(args.area):
                print_stage(enemies, found, args.skills)

        case "stage":
            print_stage(enemies, enemies.stages[args.stage], args.skills)

        case "chimera":
            print_chimera(enemies, args.difficulty)


def print_stage(enemies: Enemies, stage: Stage, with_skills: bool) -> None:
    print(f"== {stage.id}  {stage.area} / {stage.region} / {stage.difficulty}")
    print(f"   team of {stage.team_size}", end="")

    if cap := enemies.shield_caps.get(stage.area or ""):
        print(f", shields capped at {cap:,.0f}", end="")

    print()

    for restriction in stage.restrictions:
        print(f"   every champion: {describe_restriction(restriction)}")

    for number, line in enumerate(stage.formations, 1):
        if len(stage.formations) > 1:
            print(f"   formation {number}")

        for placement in line:
            print_enemy(enemies, stage, placement, with_skills)

    print()


def print_enemy(enemies: Enemies, stage: Stage, placement, with_skills: bool) -> None:
    enemy = enemies.types[placement.type_id]
    boss = f" [{enemy.boss_kind}]" if enemy.boss_kind else ""
    print(
        f"   wave {placement.wave} slot {placement.slot}: {enemy.name} ({enemy.id}){boss}"
        f" {placement.grade}* L{placement.level}"
    )

    for index, form in enumerate(enemy.forms):
        label = f"{CHIMERA_FORMS[index]:8} " if enemy.boss_kind == "Chimera" else ""
        stats = enemy_stats(stage, placement, enemy, index)
        print(f"     {label}{form.affinity:6} {format_stats(stats)}")

        if not with_skills:
            continue

        for skill_id in form.skills:
            if skill := enemies.skills.get(skill_id):
                cooldown = f" (cooldown {skill.cooldown})" if skill.cooldown else ""
                print(f"       - {skill.name}{cooldown}: {' '.join(skill.description.split())}")


def print_chimera(enemies: Enemies, difficulty: str) -> None:
    chimera = enemies.chimera
    sequence = ", ".join(f"to turn {t}: {f}" for t, f in sorted(chimera.forms_by_turn.items()))
    print(f"forms ({chimera.turns_between_forms} turns each): {sequence}")
    tier = next(t for t in chimera.tiers if t.difficulty == difficulty)
    print(f"{tier.difficulty}: HP {tier.health:,}, stages {', '.join(map(str, tier.stages))}\n")

    for trial in tier.trials:
        unit = "damage" if trial.damage else "count"
        print(f"{trial.form:5} {trial.part:4} {trial.level:6} {trial.target:>14,.0f} {unit}")
        print(f"      {' '.join(trial.description.split())}")


def describe_restriction(restriction: Restriction) -> str:
    parts = [
        ("faction", restriction.factions),
        ("role", restriction.roles),
        ("rarity", restriction.rarities),
        ("affinity", restriction.affinities),
    ]
    return "; ".join(f"{name} {' / '.join(values)}" for name, values in parts if values) or "any"


def format_stats(stats) -> str:
    def shown(stat: Stat) -> str:
        value = stats[stat]
        return (
            f"{stat.name} {value:.0%}"
            if stat in (Stat.CR, Stat.CD)
            else f"{stat.name} {value:,.0f}"
        )

    return "  ".join(shown(stat) for stat in SHOWN_STATS)


if __name__ == "__main__":
    main()
