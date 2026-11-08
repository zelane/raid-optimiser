"""
extract_assets.py - icons and portraits from the game's Unity bundles, for the web UI.

    uv run --group assets python -I tools/extract_assets.py

Writes webui/static/assets/:
  portraits/<type id with the ascension digit 0>.png  (HeroAvatars* bundles)
  sets/<set id>.png                                   (ArtifactSets)
  pieces/<set id>_<slot>.png, pieces/<faction>_<slot>.png  (Artifacts: the piece art the
                                                       game shows; faction accessories)

Bundles ship with the install (StreamingAssets) and are downloaded later (resources/); for
each family the newest version wins. Set sprites are named after the game's set names, the
display names, HH's names or an old name in `ALIASES`; a sprite that is a prefix of exactly
one game set name matches it too. Anything unmatched is listed, and the UI shows text instead.

- `GAME`, `OUT`, `SLOTS`, `ALIASES`: where things are, and the names the sprites use
- `main`: the workflow
- `bundles`, `set_keys`, `match_set`, `save`: its steps
"""

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

import UnityPy

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path(
    os.environ.get(
        "RAID_PREFIX", Path.home() / ".local/share/Steam/steamapps/compatdata/2441943673/pfx"
    )
)
GAME = (
    PREFIX / "drive_c/users/steamuser/AppData/Local/PlariumPlay/StandAloneApps/raid-shadow-legends"
)
OUT = ROOT / "webui" / "static" / "assets"
# Sprite slot suffix -> the optimiser's slot name (`Slot` member, lower case).
SLOTS = {
    "Weapon": "weapon",
    "Helmet": "helmet",
    "Shield": "shield",
    "Gloves": "gloves",
    "Chest": "chest",
    "Boots": "boots",
    "Ring": "ring",
    "Pendant": "amulet",
    "Banner": "banner",
}
# Old sprite names -> the set's display name (named by hand; accessory sets have no icon).
ALIASES = {
    "Berserker": "Crit Damage",
    "Healing": "Regeneration",
    "Rage": "Killstroke",
    "Stalwart2": "Defiant",
    "Taunting": "Provoke",
    "Warrior": "Cruel",
}
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def main() -> None:
    keys = set_keys()
    champions = json.load(open(ROOT / "captures" / "latest" / "champions.json"))
    factions = {c["Faction"] for c in champions}  # the capture's names match the sprites'
    unmatched: set[str] = set()
    written: dict[str, set[str]] = {"portraits": set(), "sets": set(), "pieces": set()}

    # 1. Portraits: sprites named by base type id.
    for sprite in sprites("HeroAvatars"):
        if (name := sprite.m_Name).isdigit():
            save(sprite, "portraits", name, written)

    # 2. Set icons.
    for sprite in sprites("ArtifactSets"):
        if (set_id := match_set(sprite.m_Name, keys)) is None:
            unmatched.add(sprite.m_Name)
            continue

        save(sprite, "sets", str(set_id), written)

    # 3. Piece art, by set and slot, or faction and slot for faction accessories.
    for sprite in sprites("Artifacts"):
        owner, _, suffix = sprite.m_Name.rpartition("_")
        if suffix not in SLOTS:
            continue

        if owner in factions:
            save(sprite, "pieces", f"{owner}_{SLOTS[suffix]}", written)
        elif (set_id := match_set(owner, keys)) is not None:
            save(sprite, "pieces", f"{set_id}_{SLOTS[suffix]}", written)

    print(", ".join(f"{len(keys)} {kind}" for kind, keys in written.items()), f"-> {OUT}")
    if unmatched:
        print("set icons with no matching set (shown as text):", ", ".join(sorted(unmatched)))


def sprites(family: str) -> Iterator:
    """Sprites from every bundle of a family, oldest version first so newer ones overwrite."""
    for path in bundles(family):
        for obj in UnityPy.load(str(path)).objects:
            if obj.type.name == "Sprite":
                yield obj.read()


def bundles(family: str) -> list[Path]:
    shipped = GAME.glob(f"build/Raid_Data/StreamingAssets/AssetBundles/{family}*/*/*/*/*.unity3d")
    downloaded = GAME.glob(f"resources/{family}_*/*/__data")
    wanted = re.compile(rf"/{re.escape(family)}(_\d+)?(_[\d.]+)?/")  # not e.g. ArtifactsForge
    found = [path for path in [*shipped, *downloaded] if wanted.search(str(path))]
    return sorted(found, key=version_of)


def version_of(path: Path) -> tuple[int, ...]:
    match = VERSION.search(str(path))
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def set_keys() -> dict[str, int]:
    """Normalised set name -> set id, from the game's, the display and HH's names."""
    enum = json.load(open(ROOT / "schema" / "schema.json"))["enums"]["ArtifactSetKindId"]
    by_game_name = {name: int(number) for number, name in enum.items()}
    keys = {normalise(name): set_id for name, set_id in by_game_name.items()}

    for raw in json.load(open(ROOT / "static" / "sets.json")):
        if raw["name"]:
            keys.setdefault(normalise(raw["name"]), by_game_name[raw["id"]])

    for name, set_id in json.load(open(ROOT / "captures" / "latest" / "set_ids.json")).items():
        keys.setdefault(normalise(name), set_id)

    keys.pop("none", None)
    return keys


def match_set(sprite_name: str, keys: dict[str, int]) -> int | None:
    """The set a sprite is named after: by alias, exactly, or as the prefix of one set's name."""
    key = normalise(ALIASES.get(sprite_name, sprite_name))
    if key in keys:
        return keys[key]

    prefixed = {set_id for name, set_id in keys.items() if name.startswith(key)}
    return prefixed.pop() if key and len(prefixed) == 1 else None


def save(sprite, kind: str, key: str, written: dict[str, set[str]]) -> None:
    """Write the sprite's image (a newer bundle's overwrites an older one's)."""
    image = sprite.image
    if image.width == 0:
        return

    folder = OUT / kind
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / f"{key}.png")
    written[kind].add(key)


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


if __name__ == "__main__":
    main()
