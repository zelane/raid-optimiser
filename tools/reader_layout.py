"""reader_layout.py - what the memory reader (`reader/`) needs to know about the game's types,
looked up by name in an Il2CppDumper dump, so a game update only needs `just dump` and a rerun.

- `CLASSES`: per class, the fields the reader reads (instance or static), as `Class.Field`
- `ROOTS`: the classes whose type info the reader starts from
- `ENUMS`: the enums whose names the reader's output is translated with (`tools.reader_export`)
- `Dump`, `parse_dump`: field offsets and enum tables from `dump.cs`
- `type_info_rvas`: where `script.json` puts classes' type info pointers in GameAssembly.dll
- `main`: writes it all as one JSON file

    uv run python -m tools.reader_layout data/dump/<version> data/cache/reader-layout.json
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import click

CLASSES = {
    ("Client.Model", "AppModel"): ("<UserId>k__BackingField", "_userWrapper"),
    ("Client.Model.Guard", "UserWrapper"): (
        "Heroes",
        "Artifacts",
        "Village",
        "Arena",
        "Inbox",
        "Relics",
        "Arena3x3",
        "Stages",
    ),
    ("Client.Model.Gameplay.Heroes", "HeroesWrapperReadOnly"): ("HeroData",),
    ("SharedModel.Meta.Heroes", "UserHeroData"): ("HeroById", "HeroesAiPresets"),
    ("SharedModel.Meta.Heroes", "HeroesAiPreset"): (
        "Id",
        "Name",
        "SkillPrioritiesSetups",
        "TypeRanges",
    ),
    ("SharedModel.Meta.Heroes", "SkillPrioritiesSetup"): ("HeroId",),
    ("SharedModel.Meta.Heroes", "Hero"): (
        "Id",
        "TypeId",
        "Grade",
        "Level",
        "EmpowerLevel",
        "Skills",
        "MasteryData",
        "DoubleAscendData",
        "Marker",
    ),
    ("SharedModel.Meta.Skills", "Skill"): ("TypeId", "Level"),
    ("SharedModel.Meta.Masteries", "HeroMasteryData"): ("Masteries", "CurrentAmount"),
    ("SharedModel.Meta.DoubleAscend.User", "HeroDoubleAscendData"): ("Grade",),
    ("Client.Model.Gameplay.Artifacts", "EquipmentWrapperReadonly"): ("ArtifactData",),
    ("SharedModel.Meta.Artifacts", "UserArtifactData"): (
        "Artifacts",
        "ArtifactDataByHeroId",
        "StorageMigrationState",
    ),
    ("SharedModel.Meta.Artifacts", "HeroArtifactData"): ("ArtifactIdByKind",),
    ("SharedModel.Meta.Artifacts.ArtifactStorage", "ArtifactStorageResolver"): ("_implementation",),
    ("Client.Model.Gameplay.Artifacts", "ExternalArtifactsStorage"): (
        "_cachedArtifacts",
        "_presets",
    ),
    ("Client.Model.Gameplay.Artifacts", "CachedArtifacts"): ("_artifacts",),
    ("Client.Model.Gameplay.Artifacts.Presets", "ArtifactPresets"): ("_presets",),
    ("SharedModel.Meta.Artifacts.Presets", "ArtifactsPresetsOfType"): (
        "_artifactPresets",
        "_accessoryPresets",
    ),
    ("SharedModel.Meta.Artifacts.Presets", "ArtifactPreset"): ("_id", "_name", "_artifactIds"),
    ("SharedModel.Meta.Artifacts", "Artifact"): (
        "_id",
        "_level",
        "_ascendLevel",
        "_kindId",
        "_variantId",
        "_rankId",
        "_rarityId",
        "_primaryBonus",
        "_secondaryBonuses",
        "_ascendBonus",
        "_setKindId",
        "_requiredFraction",
        "_rerollsCount",
    ),
    ("SharedModel.Meta.Artifacts.Bonuses", "ArtifactBonus"): (
        "_kindId",
        "_value",
        "_powerUpValue",
        "_level",
    ),
    ("SharedModel.Meta.Artifacts", "BonusValue"): ("_isAbsolute", "_value"),
    ("Client.Model.Gameplay.Village", "VillageWrapperReadOnly"): ("VillageData",),
    ("SharedModel.Meta.Village", "UserVillageData"): ("CapitolBonusLevelByStatByElement",),
    ("Client.Model.Gameplay.Battle", "ArenaWrapperReadOnly"): ("LeagueId", "ArenaData"),
    ("SharedModel.Meta.Battle.Arena", "UserArenaData"): ("DefenseHeroIds",),
    ("Client.Model.Gameplay.Arena3x3", "Arena3x3WrapperReadOnly"): ("Data",),
    ("SharedModel.Meta.Battle.Arena3x3", "UserArena3X3Data"): ("Arena3X3DefenseTeamSetup",),
    ("SharedModel.Battle.Core.Setup", "TeamSetup"): ("HeroSlotSetups",),
    ("SharedModel.Battle.Core.Setup", "HeroSlotSetup"): ("InventoryHeroId",),
    ("SharedModel", "SharedModelManager"): ("DynamicData",),
    ("SharedModel.Meta", "DynamicData"): ("StageData",),
    ("SharedModel.Meta.Stages", "DynamicStageData"): ("AllianceChimeraData",),
    ("SharedModel.Meta.Stages.Entities", "ChimeraData"): (
        "RaidStartTime",
        "RaidNumber",
        "PrizeOffset",
    ),
    ("Client.Model.Gameplay.Inbox", "InboxWrapperReadOnly"): ("InboxData",),
    ("SharedModel.Meta.Inbox", "UserInboxData"): ("Items",),
    ("SharedModel.Meta.Inbox", "InboxItem"): ("Id", "TypeId", "Prize"),
    ("SharedModel.Meta.UserPrizes", "UserPrize"): ("Artifacts",),
    ("Client.Model.Gameplay.Relics", "RelicsWrapperReadonly"): ("RelicsData",),
    ("SharedModel.Meta.Relics.UserData", "UserRelicData"): ("Relics", "RelicDataByHeroId"),
    ("SharedModel.Meta.Relics.UserData", "Relic"): ("Id", "TypeId", "Rank", "Level"),
    ("SharedModel.Meta.Relics.UserData", "HeroRelicData"): ("RelicIds",),
    ("Client.Model.Gameplay.Stages", "StageWrapperReadOnly"): ("StageData",),
    ("SharedModel.Meta.Stages", "UserStageData"): ("BattleResultsByStageId",),
    ("SharedModel.Meta.Stages", "StageStats"): ("Passed", "Stars"),
}
ROOTS = (
    "Client.Model.AppModel",
    "SharedModel.Meta.Artifacts.ArtifactStorage.ArtifactStorageResolver",
    "SharedModel.SharedModelManager",
    "SharedModel.Meta.Heroes.HeroesAiPreset",
)
ENUMS = {
    ("SharedModel.Battle.Effects", "StatKindId"),
    ("SharedModel.Meta.Artifacts.Sets", "ArtifactSetKindId"),
    ("SharedModel.Meta.Artifacts", "ArtifactKindId"),
    ("SharedModel.Meta", "ItemRarity"),
    ("SharedModel.Meta.Artifacts", "ArtifactVariantId"),
    ("SharedModel.Meta.Heroes", "HeroFraction"),
    ("SharedModel.Meta.Heroes", "Element"),
    ("SharedModel.Meta.Battle.Arena", "ArenaLeagueId"),
    ("SharedModel.Meta.Inbox", "InboxTypeId"),
    ("SharedModel.Meta.Heroes", "HeroesAiPresetType"),
    ("SharedModel.Meta.Heroes", "HeroMarker"),
    ("SharedModel.Meta.Masteries", "MasteryPointType"),
}

NAMESPACE = re.compile(r"^// Namespace: ?(.*)$")
TYPE = re.compile(r"^\S.*\b(class|struct|enum) ([\w.`<>, ]+?)(?: : [^/]+)? // TypeDefIndex")
FIELD = re.compile(r"^\t.*? (\S+); // 0x([0-9A-F]+)$")
CONST = re.compile(r"^\tpublic const \S+ (\w+) = (-?\d+);$")
BACKING = re.compile(r"^<(\w+)>k__BackingField$")


@dataclass(frozen=True)
class Dump:
    fields: dict[str, int]  # Class.Field (backing fields by their property's name)
    enums: dict[str, dict[int, str]]  # Enum -> value -> name


def parse_dump(dump_cs: Path) -> Dump:
    """The offsets of `CLASSES`' fields and the values of `ENUMS`."""
    wanted = {(ns, cls, field) for (ns, cls), fields in CLASSES.items() for field in fields}
    fields: dict[str, int] = {}
    enums: dict[str, dict[int, str]] = {}
    namespace, cls, kind = "", "", ""

    with dump_cs.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            if m := NAMESPACE.match(line):
                namespace = m.group(1)
            elif m := TYPE.match(line):
                kind, cls = m.groups()
            elif kind == "enum" and (namespace, cls) in ENUMS and (m := CONST.match(line)):
                enums.setdefault(cls, {})[int(m.group(2))] = m.group(1)
            elif kind != "enum" and (m := FIELD.match(line)):
                if (namespace, cls, m.group(1)) in wanted:
                    name = BACKING.sub(r"\1", m.group(1))
                    fields[f"{cls}.{name}"] = int(m.group(2), 16)

    return Dump(fields, enums)


def type_info_rvas(script_json: Path) -> dict[str, int]:
    """The RVA of each root's `<Class>_TypeInfo` pointer."""
    names = {f"{root}_TypeInfo": root for root in ROOTS}
    entries = json.loads(script_json.read_text())["ScriptMetadata"]
    return {names[entry["Name"]]: entry["Address"] for entry in entries if entry["Name"] in names}


def missing(dump: Dump, roots: dict[str, int]) -> list[str]:
    """What the dump doesn't have."""
    fields = [
        f"{cls}.{BACKING.sub(r'\1', field)}"
        for (_, cls), names in CLASSES.items()
        for field in names
    ]
    return (
        [field for field in fields if field not in dump.fields]
        + [name for _, name in ENUMS if name not in dump.enums]
        + [f"{root}_TypeInfo" for root in ROOTS if root not in roots]
    )


@click.command()
@click.argument("dump_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("out", type=click.Path(dir_okay=False, path_type=Path))
def main(dump_dir: Path, out: Path) -> None:
    dump = parse_dump(dump_dir / "dump.cs")
    roots = type_info_rvas(dump_dir / "script.json")

    if absent := missing(dump, roots):
        raise click.ClickException(f"not in {dump_dir}: {', '.join(absent)}")

    layout = {
        "game_version": dump_dir.name,
        "type_info": roots,
        "fields": dump.fields,
        "enums": dump.enums,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(layout, indent=2))
    click.echo(f"{len(dump.fields)} fields, {len(dump.enums)} enums for {dump_dir.name} -> {out}")


if __name__ == "__main__":
    main()
