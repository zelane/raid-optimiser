"""
setups.py - fights' setups for the battle host (`host/`), from the account: what the game sends
for a fight (`BattleSetup`), with the player's team swapped for any champions, in what they wear.
A slot (`HeroSlotSetup`) is the account's champion as it is (rank, level, skills, masteries,
skill settings) plus the parts the game computes (gear and sets, Blessing, Academy, Great Hall,
relic), which the host builds with the game's own code from the game's own objects (`build`).
So this module writes the snapshot as the game's JSON (its short keys, enums as numbers, values
as `Fixed`), and puts the host's parts into slots.

The enemy's side and the stage come from the stage's static data (`stage_setup`: its formation
and modifiers, enemies' skills at level 1), or from a captured setup (`just capture`), whose
enemies are as the server sent them: the template.

- `Enums`: the game's enums by name (schema/schema.json)
- `build_request`: what the host's `build` needs for some champions
- `stage_setup`: a stage's setup with no team yet, from the static data
- `team_setup`: the template with the player's team made of the champions given
- `slot`, `skill_setups`: one champion's slot, from the account and its built parts
- `Relics`, `relic_setup`: a worn relic's skills and its stones' (the game's builder gives only
  its stats; the server adds the skills, which the static data names)
- `assemble`: a whole setup from the account, the host's parts and a template (`main`)
- `game_hero`, `game_artifact`, `game_bonus`, `game_relic`, `game_village`, `game_guardians`,
  `skill_settings`: the snapshot's records as the game's JSON
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from optimiser.paths import GAME, SCHEMA, SNAPSHOT
from optimiser.tables import faction_name

CRIT_KEYS = frozenset({"u", "m"})  # BattleStats' C.RATE and C.DMG
ENEMY = -1  # the enemy side's owner id


@dataclass(frozen=True)
class Enums:
    """Each enum's numbers by name."""

    by_name: dict[str, dict[str, int]]

    @staticmethod
    def load(schema: Path) -> "Enums":
        enums = json.loads(schema.read_text())["enums"]
        return Enums(
            {e: {name: int(v) for v, name in values.items()} for e, values in enums.items()}
        )

    def value(self, enum: str, name: str) -> int:
        return self.by_name[enum][name]


def build_request(snapshot: dict, champion_ids: list[int], enums: Enums) -> dict:
    """The host's `build` request: the account's Academy and Great Hall, and each champion as
    the game's `Hero`, with the pieces and relics they wear."""
    heroes = {h["id"]: h for h in snapshot["heroes"]}
    artifacts = {a["id"]: a for a in snapshot["artifacts"]}
    relics = {r["id"]: r for r in snapshot["relics"]}

    def champion(hero_id: int) -> dict:
        hero = heroes[hero_id]
        worn = snapshot["equipped"].get(str(hero_id), [])
        worn_relics = snapshot["worn_relics"].get(str(hero_id), [])
        return {
            "type_id": hero["type_id"],
            "hero": game_hero(hero),
            "artifacts": {"r": [game_artifact(artifacts[i], enums) for i in worn]},
            "relics": {
                "r": [game_relic(relics[i]) for i in worn_relics],
                "s": [{"i": s["id"], "t": s["type_id"]} for s in snapshot.get("relic_stones", [])],
            },
        }

    return {
        "guardians": game_guardians(snapshot["academy_guardians"], enums),
        "village": game_village(snapshot["great_hall"], enums),
        "champions": [champion(i) for i in champion_ids],
    }


PVE = 1  # BattleKindId


def stage_setup(stage_id: int, snapshot: dict, enums: Enums, preset: int | None) -> dict:
    """A `BattleSetup` for a stage, as the server would send it, the player's team still
    empty: the stage's enemies (its first formation, every wave), with their skills at level 1,
    its stat modifiers, and the server's turn limit. Checked against a captured Ice Golem Hard 10
    setup: the same but for the fields about rewards (multiplier, double runs, run number)."""
    stage = json.loads((GAME / "enemies.json").read_text())["stages"][str(stage_id)]
    types = {t["id"]: t for t in json.loads((GAME / "hero_types.json").read_text())}

    def enemy(placement: dict) -> dict:
        forms = types[placement["type"]]["forms"]
        return {
            "d": placement["wave"],
            "t": placement["slot"],
            "u": ENEMY,
            "i": placement["type"],
            "h": 0,
            "g": placement["grade"],
            **({"w": placement["awakened"]} if placement.get("awakened") else {}),
            "l": placement["level"],
            "hb": placement.get("hero_boss", False),
            "mb": placement.get("main_boss", False),
            "s": [{"i": skill, "l": 1} for form in forms for skill in form["skills"]],
        }

    modifiers = [
        {
            "r": m["wave"],
            "k": enums.value("StatKindId", m["stat"]),
            "v": m["value"],
            "a": m["absolute"],
            "b": m["boss_only"],
        }
        for m in stage["modifiers"]
    ]
    league = enums.value("ArenaLeagueId", snapshot["arena_league"] or "GoldV")
    max_turns = (snapshot.get("battle_settings") or {}).get("MaxTurnsInBattle")

    return {
        "r": 1,
        "k": PVE,
        "f": {"p": 0, "i": snapshot["user_id"], "l": league, "h": [], "ls": 0},
        "s": {
            "p": 0,
            "i": ENEMY,
            "l": 0,
            "h": [enemy(p) for p in stage["formations"][0]],
            "m": modifiers,
            "ls": 0,
        },
        "i": stage_id,
        "d": 0,
        **({"pi": preset} if preset else {}),
        **({"mt": max_turns} if max_turns else {}),  # the server's turn limit for a stage
        "bm": 1,
    }


def team_setup(template: dict, slots: list[dict]) -> dict:
    """The template's setup (its stage, enemies and settings) with the player's team made of
    `slots`, numbered in order."""
    team = dict(template["f"])
    team["h"] = [{**s, "t": n} for n, s in enumerate(slots, start=1)]
    return {**template, "f": team}


@dataclass(frozen=True)
class Relics:
    """What a worn relic's skills come from: the account's relics and stones, and the static
    data's skills (`effect_sources.json`: relic types, stone types, skill level by relic level)."""

    relics: dict[int, dict]
    stones: dict[int, dict]
    sources: dict

    @staticmethod
    def of(snapshot: dict, sources_file: Path) -> "Relics":
        return Relics(
            {r["id"]: r for r in snapshot["relics"]},
            {s["id"]: s for s in snapshot.get("relic_stones", [])},
            json.loads(sources_file.read_text()),
        )


def relic_setup(relic: dict, built: dict, relics: Relics, faction: str) -> dict:
    """A worn relic's `RelicSetup`: its skills at the level its relic level reaches (and those
    for the champion's faction, by display name), its stones' skills, and the built stats."""
    relic_type = next(r for r in relics.sources["relics"] if r["id"] == relic["type_id"])
    reached = [
        int(level) for level in relics.sources["relic_skill_levels"] if int(level) <= relic["level"]
    ]
    level = relics.sources["relic_skill_levels"][str(max(reached))]
    skills = relic_type["skills"] + relic_type["by_faction"].get(faction, [])
    stone_types = [
        relics.stones[s["stone"]]["type_id"] for s in relic.get("sockets", []) if s["stone"]
    ]
    stone_skills = [
        i for t in stone_types for i in relics.sources["relic_stones"][str(t)]["skills"]
    ]

    percent, flat = dict(built.get("p") or {}), dict(built.get("f") or {})

    for crit in CRIT_KEYS & flat.keys():  # the builder files crit as flat, the server as percent
        percent[crit] = flat.pop(crit)

    return {
        "l": level,
        "r": [{"i": i, "l": level} for i in skills],
        "s": [{"i": i, "l": 0} for i in stone_skills],
        "p": percent,
        "f": flat,
    }


def slot(
    hero: dict,
    skills: list[dict],
    parts: dict,
    settings: dict | None,
    owner: int,
    relic: dict | None,
) -> dict:
    """A champion's `HeroSlotSetup`: the account's champion with its `skill_setups`, the host's
    built parts and its relic's setup (`relic_setup`)."""
    built = {key: parts[key] for key in ("b", "e", "bl", "c", "z") if parts.get(key)}

    return {
        "d": 1,
        "u": owner,
        "i": hero["type_id"],
        "h": hero["id"],
        "g": hero["grade"],
        **({"w": hero["awakened_grade"]} if hero["awakened_grade"] else {}),
        "l": hero["level"],
        "r": hero["empower"],
        "s": skills,
        "y": hero["masteries"],
        **built,
        **({"re": relic} if relic else {}),
        **({"p": settings} if settings else {}),
    }


def skill_setups(hero: dict, form_skills: list[list[int]], skills: dict) -> list[dict]:
    """Its skills as a slot lists them: each form's in the hero type's order, at the level the
    account has (a skill that takes another's level, `use_level_of`, at that one's)."""
    levels = {int(i): level for i, level in hero["skills"].items()}

    def level(skill_id: int) -> int:
        source = skills.get(str(skill_id), {}).get("use_level_of", skill_id)
        return levels.get(source, levels.get(skill_id, 1))

    return [{"i": i, "l": level(i)} for form in form_skills for i in form if i in levels]


def game_hero(hero: dict) -> dict:
    return {
        "i": hero["id"],
        "t": hero["type_id"],
        "g": hero["grade"],
        "l": hero["level"],
        "e": hero["empower"],
        "s": [{"t": int(i), "l": level} for i, level in hero["skills"].items()],
        "m": {"m": hero["masteries"]},
        "da": {"g": hero["awakened_grade"], "b": hero.get("blessing")},
    }


def game_artifact(piece: dict, enums: Enums) -> dict:
    ascend = {"ab": game_bonus(piece["ascend"], enums)} if piece.get("ascend") else {}
    return {
        "i": piece["id"],
        "l": piece["level"],
        "al": piece.get("ascend_level"),
        "k": enums.value("ArtifactKindId", piece["kind"]),
        "vr": enums.value("ArtifactVariantId", piece["variant"]),
        "r": piece["rank"],
        "a": enums.value("ItemRarity", piece["rarity"]),
        "p": game_bonus(piece["primary"], enums),
        "e": [game_bonus(line, enums) for line in piece["substats"]],
        "t": piece["set"],
        "f": enums.value("HeroFraction", piece["faction"]),
        "rl": piece.get("rerolls"),
        **ascend,
    }


def game_bonus(line: dict, enums: Enums) -> dict:
    """A stat line (`ArtifactBonus`): its values as the game's `Fixed`, from the reader's raw
    ones where it has them."""
    value = line.get("value_fixed", round(line["value"] * 2**32))
    glyph = line.get("glyph_fixed", round(line["glyph"] * 2**32))
    by_rarity = (
        {"r": line["rarity_glyph_fixed"]} if line.get("rarity_glyph_fixed") is not None else {}
    )
    rarity = {"i": line["glyph_rarity"]} if line.get("glyph_rarity") is not None else {}
    return {
        "k": enums.value("StatKindId", line["stat"]),
        "p": {"a": line["absolute"], "v": value},
        "s": glyph,
        "l": line["rolls"],
        **by_rarity,
        **rarity,
    }


def game_relic(relic: dict) -> dict:
    return {
        "i": relic["id"],
        "t": relic["type_id"],
        "a": relic["rank"],
        "l": relic["level"],
        "k": [{"k": s["shape"], "s": s["stone"]} for s in relic.get("sockets", [])],
    }


def game_village(great_hall: dict, enums: Enums) -> dict:
    """The Great Hall's levels, as `UserVillageData.CapitolBonusLevelByStatByElement`."""
    return {
        "s": {
            str(enums.value("Element", element)): {
                str(enums.value("StatKindId", stat)): level for stat, level in stats.items()
            }
            for element, stats in great_hall.items()
        }
    }


def game_guardians(guardians: dict, enums: Enums) -> dict:
    return {
        "s": {
            str(enums.value("HeroFraction", faction)): {
                "s": {
                    str(enums.value("HeroRarity", rarity)): [
                        {
                            "f": s["first_hero"],
                            "s": s["second_hero"],
                            "c": s["consumed"],
                            "b": s["hero_base_type_id"],
                        }
                        for s in slots
                    ]
                    for rarity, slots in by_rarity.items()
                }
            }
            for faction, by_rarity in guardians.items()
        }
    }


def skill_settings(snapshot: dict, preset_id: int, hero_id: int) -> dict | None:
    """A champion's skill settings in a saved team, as a slot's `SkillPrioritiesSetup`."""
    preset = next((p for p in snapshot["presets"] if p["id"] == preset_id), None)
    setup = next((s for s in (preset or {}).get("priorities", []) if s["hero_id"] == hero_id), None)

    if setup is None:
        return None

    names = {"Default": 0, "First": 1, "Second": 2, "Third": 3, "NotUsed": 4}
    sequences = [
        {
            **({"i": seq["starters"]} if seq["starters"] else {}),
            "p": {k: names[v] for k, v in seq["priorities"].items()},
        }
        for seq in setup["sequences"]
    ]
    return {"h": hero_id, "r": sequences}


def assemble(
    snapshot: dict, parts: list[dict], template: dict, champion_ids: list[int], preset: int | None
) -> dict:
    """The template with the champions as its team: each slot from the account and its built
    parts, with skill settings from the saved team `preset`, else the template's own for the
    same champion, else none (auto's defaults)."""
    heroes = {h["id"]: h for h in snapshot["heroes"]}
    types = {t["id"]: t for t in json.loads((GAME / "hero_types.json").read_text())}
    skills = json.loads((GAME / "skills.json").read_text())
    relics = Relics.of(snapshot, GAME / "effect_sources.json")
    template_settings = {s["h"]: s.get("p") for s in template["f"]["h"]}

    def one(hero_id: int, built: dict) -> dict:
        hero = heroes[hero_id]
        hero_type = types[hero["type_id"]]
        worn = snapshot["worn_relics"].get(str(hero_id), [])
        relic = (
            relic_setup(
                relics.relics[worn[0]],
                (built.get("re") or [{}])[0],
                relics,
                faction_name(hero_type["fraction"]),
            )
            if worn
            else None
        )
        settings = (
            skill_settings(snapshot, preset, hero_id) if preset else None
        ) or template_settings.get(hero_id)
        form_skills = [form["skills"] for form in hero_type["forms"]]
        return slot(
            hero,
            skill_setups(hero, form_skills, skills),
            built,
            settings,
            snapshot["user_id"],
            relic,
        )

    return team_setup(template, [one(i, b) for i, b in zip(champion_ids, parts, strict=True)])


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request", help="what the host's build needs")
    request.add_argument("out", type=Path)
    request.add_argument("champions", type=int, nargs="+")
    setup = commands.add_parser("assemble", help="the setup, from the host's built parts")
    setup.add_argument(
        "against", help="a stage id (its static data), or a captured setup's file: its enemies"
    )
    setup.add_argument("parts", type=Path)
    setup.add_argument("out", type=Path)
    setup.add_argument("champions", type=int, nargs="+")
    setup.add_argument("--preset", type=int, help="the saved team whose skill settings to use")
    args = parser.parse_args()
    snapshot = json.loads(SNAPSHOT.read_text())

    match args.command:
        case "request":
            args.out.write_text(
                json.dumps(build_request(snapshot, args.champions, Enums.load(SCHEMA)))
            )
        case "assemble":
            parts = json.loads(args.parts.read_text())
            template = (
                stage_setup(int(args.against), snapshot, Enums.load(SCHEMA), args.preset)
                if args.against.isdigit()
                else json.loads(Path(args.against).read_text())
            )
            setup_json = assemble(snapshot, parts, template, args.champions, args.preset)
            args.out.write_text(json.dumps(setup_json))


if __name__ == "__main__":
    main()
