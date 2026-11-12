"""
extract_assets.py - icons and portraits from the game's Unity bundles, for the web UI.

    uv run --group assets python -I tools/extract_assets.py

Writes webui/static/assets/:
  portraits/<type id with the ascension digit 0>.png  (HeroAvatars, HeroAvatarsLocal,
                                                     FuseAvatarsLocal bundles; the sprite
                                                     the type's "avatar" names, if another)
  sets/<set id>.png                                   (ArtifactSets)
  pieces/<set id>_<slot>.png, pieces/<faction>_<slot>.png  (Artifacts: the piece art the
                                                       game shows; faction accessories)
  affinities/<magic|force|spirit|void>.png             (HeroElements)
  factions/<faction, as the capture names it>.png     (FractionAvatars: the banners)
  stars/<yellow|purple|red>.png                       (UIShared: plain, ascended, awakened)
  frames/<rarity, lower case>.png                     (UIShared: 9-slice portrait frames; no
                                                       Uncommon. app.css holds their slices)
  forms/<1|2>.png, forms/<1|2>-white.png              (MetamorphSwitchButton: a mythical's
                                                       form, gold when chosen, else white)
  ui/<name>.png                                       (UIShared: `UI_SPRITES`, the game's panel
                                                       frame and rarity crests)

Bundles ship with the install (StreamingAssets) and are downloaded later (resources/); for
each family the newest version wins. Set sprites are named after the game's set names, the
display names, HH's names or an old name in `ALIASES`; a sprite that is a prefix of exactly
one game set name matches it too. Anything unmatched is listed, and the UI shows text instead.

- `GAME`, `OUT`, `TABLES`, `CAPTURES`, `SLOTS`, `ALIASES`: where things are, and the names the sprites use
- `main`: the workflow
- `bundles`, `set_keys`, `match_set`, `save`: its steps
"""

import json
import os
import re
import shutil
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
TABLES = ROOT / "data" / "game"  # the game's tables (update-static.sh)
CAPTURES = ROOT / "data" / "captures" / "latest"
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
AFFINITIES = ("magic", "force", "spirit", "void")
STARS = {"big_star": "yellow", "big_ascend_star": "purple", "big_red_star": "red"}
FRAMES = ("Common", "Rare", "Epic", "Legendary", "Mythical")
# The game's UI pieces the web UI dresses itself in -> their names there. The panel frame is
# a 9-slice (28 px slices; app.css holds them).
UI_SPRITES = {
    "bg_background_runs": "panel",
    "MythicalDecorTop": "crest-mythical",
    "MythicalDecorBottom": "crest-mythical-bottom",
    "LegendaryDecor": "crest-legendary",
    "EpicDecor": "crest-epic",
}
# Mythical form switch sprites -> form number and state: winged helm 1, horned helm 2.
FORM_ICONS = {
    "metamorph_switch_form_button1": "1",
    "metamorph_switch_form_button1_white": "1-white",
    "metamorph_switch_form_button2": "2",
    "metamorph_switch_form_button2_white": "2-white",
}
PORTRAIT_FAMILIES = ("HeroAvatars", "HeroAvatarsLocal", "FuseAvatarsLocal")
PLACEHOLDER_PORTRAIT = re.compile(r"(\d+)(?:_?temp|_avatar)")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def main() -> None:
    keys = set_keys()
    champions = json.load(open(CAPTURES / "champions.json"))
    factions = {c["Faction"] for c in champions}  # the capture's names match the sprites'
    unmatched: set[str] = set()
    written: dict[str, set[str]] = {
        kind: set()
        for kind in (
            "portraits", "sets", "pieces", "affinities", "factions", "stars", "frames", "forms", "ui"
        )
    }

    # 1. Portraits: sprites named by base type id. Fusion champions' (and a few others')
    # ship in their own local bundles.
    # Placeholders ("1770_temp", "6480_avatar") only where there's no proper one.
    placeholders = {}

    for family in PORTRAIT_FAMILIES:
        for sprite in sprites(family):
            if (name := sprite.m_Name).isdigit():
                save(sprite, "portraits", name, written)
            elif placeholder := PLACEHOLDER_PORTRAIT.fullmatch(name):
                placeholders[placeholder[1]] = sprite

    for name, sprite in placeholders.items():
        if name not in written["portraits"]:
            save(sprite, "portraits", name, written)

    # Types whose portrait is another sprite (`hero_types.json` "avatar") get that one, as the
    # game shows it, even where a sprite has their own id.
    for hero_type in json.load(open(TABLES / "hero_types.json")):
        key, avatar = str(hero_type["id"]), hero_type.get("avatar")
        if avatar and avatar != key and avatar in written["portraits"]:
            shutil.copyfile(OUT / "portraits" / f"{avatar}.png", OUT / "portraits" / f"{key}.png")
            written["portraits"].add(key)

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

    # 4. Affinity icons.
    for sprite in sprites("HeroElements"):
        if sprite.m_Name in AFFINITIES:
            save(sprite, "affinities", sprite.m_Name, written)

    # 5. Faction banners, named by the game's faction number.
    faction_names = capture_faction_names(champions)

    for sprite in sprites("FractionAvatars"):
        if name := faction_names.get(sprite.m_Name):
            save(sprite, "factions", name, written)

    # 6. Champion stars (plain, ascended and awakened), portrait frames by rarity, and the UI
    # pieces (panel frame, rarity crests).
    for sprite in sprites("UIShared"):
        if colour := STARS.get(sprite.m_Name):
            save(sprite, "stars", colour, written)
        elif sprite.m_Name in FRAMES:
            save(sprite, "frames", sprite.m_Name.lower(), written)
        elif name := UI_SPRITES.get(sprite.m_Name):
            save(sprite, "ui", name, written)

    # 7. A mythical's form switch: its two helms.
    for sprite in sprites("MetamorphSwitchButton"):
        if key := FORM_ICONS.get(sprite.m_Name):
            save(sprite, "forms", key, written)

    print(", ".join(f"{len(keys)} {kind}" for kind, keys in written.items()), f"-> {OUT}")
    if missing := factions - written["factions"]:
        print("factions with no banner:", ", ".join(sorted(missing)))
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


def capture_faction_names(champions: list[dict]) -> dict[str, str]:
    """The game's faction number (as text) -> the capture's name for it. HH renames a few
    (Samurai -> Shadowkin, Olympians -> Argonites), so pair them up by champion type."""
    enum = json.load(open(ROOT / "schema" / "schema.json"))["enums"]["HeroFraction"]
    number_of = {name: number for number, name in enum.items()}
    game_faction = {t["id"]: t["fraction"] for t in json.load(open(TABLES / "hero_types.json"))}
    names = {}

    for champion in champions:
        if game_name := game_faction.get(champion["TypeId"] // 10 * 10):
            names[number_of[game_name]] = champion["Faction"]

    return names


def set_keys() -> dict[str, int]:
    """Normalised set name -> set id, from the game's, the display and HH's names."""
    enum = json.load(open(ROOT / "schema" / "schema.json"))["enums"]["ArtifactSetKindId"]
    by_game_name = {name: int(number) for number, name in enum.items()}
    keys = {normalise(name): set_id for name, set_id in by_game_name.items()}

    for raw in json.load(open(TABLES / "sets.json")):
        if raw["name"]:
            keys.setdefault(normalise(raw["name"]), by_game_name[raw["id"]])

    for name, set_id in json.load(open(CAPTURES / "set_ids.json")).items():
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
