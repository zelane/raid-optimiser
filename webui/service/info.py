"""
info.py - the info page: the account's progress, read from the game. Its one section so far is
Faction Wars: per crypt, the stages at a difficulty still short of their stars, and the battle
quests they may still need.

The game keeps a count of each stage's stars, not which battle quests earned them. The first
("Beat Stage") comes with beating it, so a stage one star short is missing one of the other
two (almost always its challenge, the last), and the page says so.

- `FW_DIFFICULTY`: the difficulty the section covers (the area is `enemies.FACTION_WARS`)
- `StageRow`, `CryptView`, `FactionWarsSection`, `InfoPage`: the views
- `info_page`: what the page shows
- `faction_wars_section`, `crypt_view`, `stage_row`: its pieces
"""

from dataclasses import dataclass, replace

from optimiser.account import Account, StageProgress, faction_name
from optimiser.enemies import CRYPT, FACTION_WARS, Enemies, Region
from webui.service.teams import stage_url
from webui.service.views import asset_url

FW_DIFFICULTY = "Hard"


@dataclass(frozen=True)
class StageRow:
    """A stage short of its stars. `open`: the battle quests that may still be needed; when
    `one_of`, only one of them is (the game doesn't say which); `teams_url`: the team finder
    at it."""

    number: int
    stars: int
    state: str  # "2/3 stars", "not beaten", "not fought"
    open: tuple[str, ...]
    one_of: bool
    teams_url: str = ""


@dataclass(frozen=True)
class CryptView:
    """A crypt short of its stars: `region` is the game's id."""

    region: str
    name: str
    banner_url: str | None
    stars: int
    max_stars: int
    rows: tuple[StageRow, ...]  # the stages short of their stars, in order


@dataclass(frozen=True)
class FactionWarsSection:
    difficulty: str
    stars: int
    max_stars: int
    open_stages: int
    crypts: tuple[CryptView, ...]  # the crypts with something left, in the game's order
    done: tuple[str, ...]  # the crypts complete


@dataclass(frozen=True)
class InfoPage:
    faction_wars: FactionWarsSection


def info_page(account: Account, enemies: Enemies) -> InfoPage:
    return InfoPage(faction_wars=faction_wars_section(account, enemies, FW_DIFFICULTY))


def faction_wars_section(account: Account, enemies: Enemies, difficulty: str) -> FactionWarsSection:
    area = next(area for area in enemies.areas if area.id == FACTION_WARS)
    crypts = [crypt_view(account, enemies, region, difficulty) for region in area.regions]
    return FactionWarsSection(
        difficulty=difficulty,
        stars=sum(crypt.stars for crypt in crypts),
        max_stars=sum(crypt.max_stars for crypt in crypts),
        open_stages=sum(len(crypt.rows) for crypt in crypts),
        crypts=tuple(crypt for crypt in crypts if crypt.rows),
        done=tuple(crypt.name for crypt in crypts if not crypt.rows),
    )


def crypt_view(account: Account, enemies: Enemies, region: Region, difficulty: str) -> CryptView:
    stage_ids = region.stages.get(difficulty, ())
    stars = 0
    max_stars = 0
    rows = []

    for number, stage_id in enumerate(stage_ids, 1):
        quests = tuple(quest.text for quest in enemies.stages[stage_id].quests)
        progress = account.stages.get(stage_id)
        stars += progress.stars if progress else 0
        max_stars += len(quests)

        if (row := stage_row(number, quests, progress)) is not None:
            rows.append(replace(row, teams_url=stage_url(stage_id)))

    faction = faction_name(region.id.removeprefix(CRYPT))
    banner = asset_url("factions", faction)
    return CryptView(region.id, region.name, banner, stars, max_stars, tuple(rows))


def stage_row(
    number: int, quests: tuple[str, ...], progress: StageProgress | None
) -> StageRow | None:
    """The stage's row, if it's short of its stars."""
    match progress:
        case None:
            return StageRow(number, 0, "not fought", quests, one_of=False)

        case StageProgress(passed=False, stars=stars):
            return StageRow(number, stars, "not beaten", quests, one_of=False)

        case StageProgress(stars=stars) if stars >= len(quests):
            return None

        case StageProgress(stars=stars):
            rest = quests[1:]  # "Beat Stage" came with beating it
            missing = len(quests) - stars
            return StageRow(
                number, stars, f"{stars}/{len(quests)} stars", rest, one_of=missing < len(rest)
            )
