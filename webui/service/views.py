"""
views.py - views several pages share: a champion as a row, and how pieces and sets are named
and pictured.

- `ASSETS`: where the extracted game art lives
- `Choice`: an option of a select
- `StarView`, `ChampionRow`, `champion_row`, `star_views`, `star_colour`: a champion
- `choice_label`: a champion as a typed list names them ("Name, 6★ L60 #id": the id decides)
- `slot_value`: a champion in a team slot's field (and the URL): their id
- `set_name`, `slot_label`, `piece_image_url`: a piece
- `asset_url`: an extracted game icon
"""

from dataclasses import dataclass, field
from pathlib import Path

from optimiser.account import Account, Artifact, Champion, Slot

ASSETS = Path(__file__).resolve().parents[1] / "static" / "assets"


@dataclass(frozen=True)
class Choice:
    """An option of a select: what it sends, and what it shows."""

    value: str
    label: str


@dataclass(frozen=True)
class StarView:
    colour: str  # "red" awakened, "purple" ascended, "yellow" neither
    image_url: str | None


@dataclass(frozen=True)
class ChampionRow:
    """The defaults are for runs saved before those fields existed."""

    id: int
    name: str
    rarity: str
    grade: int
    level: int
    ascension: int
    awakening: int
    empower: int
    affinity: str
    faction: str
    portrait_url: str | None
    stars: list[StarView] = field(default_factory=list)
    affinity_icon_url: str | None = None
    faction_icon_url: str | None = None
    # The game's rarity crests (Epic up): one set over the portrait's lower edge, and for
    # Mythicals another over its top.
    crest_url: str | None = None
    crest_top_url: str | None = None


def champion_row(champion: Champion) -> ChampionRow:
    rarity = champion.rarity.lower()
    mythical = rarity == "mythical"
    return ChampionRow(
        id=champion.id,
        name=champion.name,
        rarity=champion.rarity,
        grade=champion.grade,
        level=champion.level,
        ascension=champion.ascension,
        awakening=champion.awakening,
        empower=champion.empower,
        affinity=champion.element,
        faction=champion.faction,
        portrait_url=asset_url("portraits", str(champion.type_id // 10 * 10)),  # unascended
        stars=star_views(champion.grade, champion.ascension, champion.awakening),
        affinity_icon_url=asset_url("affinities", champion.element.lower()),
        faction_icon_url=asset_url("factions", champion.faction),
        crest_url=asset_url("ui", f"crest-{rarity}-bottom" if mythical else f"crest-{rarity}"),
        crest_top_url=asset_url("ui", "crest-mythical") if mythical else None,
    )


def star_views(stars: int, ascension: int, awakening: int) -> list[StarView]:
    colours = (star_colour(star, ascension, awakening) for star in range(stars))
    return [StarView(colour, asset_url("stars", colour)) for colour in colours]


def star_colour(star: int, ascension: int, awakening: int) -> str:
    """Counting from the first star: awakened ones, then ascended ones, then plain (a
    champion is never awakened past their ascension)."""
    if star < awakening:
        return "red"

    if star < ascension:
        return "purple"

    return "yellow"


def set_name(account: Account, set_id: int) -> str:
    artifact_set = account.tables.sets.get(set_id)
    return artifact_set.name if artifact_set else "No set"


def slot_label(slot: Slot) -> str:
    return "Amulet" if slot is Slot.AMULET else slot.value


def piece_image_url(artifact: Artifact) -> str | None:
    """Set accessories share the set's art; only set-less ones show the faction's."""
    slot_key = artifact.slot.name.lower()

    if url := asset_url("pieces", f"{artifact.set_id}_{slot_key}"):
        return url

    return asset_url("pieces", f"{artifact.faction}_{slot_key}") if artifact.faction else None


def asset_url(kind: str, key: str) -> str | None:
    """An extracted game icon, if we have it; pages fall back to text otherwise."""
    if ASSETS.joinpath(kind, f"{key}.png").is_file():
        return f"/static/assets/{kind}/{key}.png"

    return None


def choice_label(champion: Champion) -> str:
    return f"{champion.name}, {champion.grade}★ L{champion.level} #{champion.id}"


def slot_value(champion: Champion) -> str:
    return str(champion.id)
