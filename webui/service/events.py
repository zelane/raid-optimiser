"""
events.py - the events page: the events and tournaments on in the game (running, coming up, and
ended with prizes still to claim), each with the account's points and place as at the last
sync, its milestones and what earns its points.

An action's rules become tables: rules setting the same fields share one, and when they vary
along two (gear's rank and rarity, its rank and upgrade level) it's a grid, the field with
more values down the side. What every rule in it shares is said once above it ("Ice Golem's
Keep"), and rows earning nothing are left out.

Titles and points' names are the game's, in its language; Plarium's own name
(which says which fusion an event is for) stays beside them.

- `PointsRow`, `PointsTable`, `MilestoneRow`, `EventCard`, `EventsPage`: the views
- `events_page`: what the page shows
- `Names`: what prizes and rules name (champions, items, sets, relics)
- `event_card`, `points_tables`, `points_table`, `milestone_rows`, `prize_text`: its pieces
- `row_label`, `condition_labels`, `points_text`, `prize_item_text`, `when_text`,
  `levels_text`, `event_name`, `kind_label`, `words`: the words
  they're shown with
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from optimiser.account import Account
from optimiser.events import (
    Condition,
    Events,
    Fragments,
    GameEvent,
    Goods,
    Milestone,
    Other,
    Pieces,
    Prize,
    PrizeItem,
    RelicPrize,
    RelicStones,
    Rule,
    Soul,
    Standing,
    TurnPoints,
    account_levels,
    milestones_for,
)
from optimiser.levelling import Levelling
from optimiser.loot import Loot
from optimiser.summons import Summoning
from webui.service.fights import STAGE_FIELDS, FightPlan, fight_plan, stages_text
from webui.service.summons import SummonPlan, summon_plan
from webui.service.training import BrewPlan, brew_plan
from webui.service.upgrades import UpgradePlan, upgrade_plan
from webui.service.views import span_text

ACTIONS = {
    "Artifact_Collect": "Get gear",
    "Artifact_Upgrade": "Upgrade gear",
    "Hero_LevelUp": "Level up champions",
    "Hero_RankUp": "Rank up champions",
    "Hero_Summon": "Summon champions",
    "Hero_Fuse": "Fuse champions",
    "Hero_Receive": "Get champions",
    "Hero_Assemble": "Assemble champions from fragments",
    "Battle_DungeonReward": "Dungeon drops",
    "Battle_DungeonTurn": "Dungeon wins, by turns",
    "Battle_Arena3X3": "Tag Team Arena wins",
    "DoubleAscend_SoulStoneOpen": "Open soulstones",
    "BlackMarketItemReceive": "Get items",
}
SOLO_KINDS = {
    "PointBased": "Event",
    "Bingo": "Bingo",
    "LimitedSoulSummon": "Limited soul summon",
    "CooperationEvent": "Co-op event",
}
TOURNAMENT_KINDS = {
    "FireGolem": "Fire Knight",
    "IceGolem": "Ice Golem",
    "SandDevilTurnAttack": "Sand Devil, by turns",
    "Arena3X3Points": "Tag Team Arena",
    "HeroAcquire": "Champion Chase",
}
RESOURCES = {"Gem": "Gems"}
RANKS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6}
FUSION = re.compile(r"^Fuse (\d+)\s*")  # Plarium's names for a fusion's events
NAME_DATE = re.compile(r"\s*,\s*\d{2}-\d{2}-\d{4}\s*$")


@dataclass(frozen=True)
class PointsRow:
    label: str
    cells: tuple[str, ...]  # a column's points; "" where no rule says


@dataclass(frozen=True)
class PointsTable:
    """`note`: what every rule in it shares; `columns`: the grid's headings, or ("Points",)."""

    action: str
    note: str
    side: str  # the rows' heading
    columns: tuple[str, ...]
    rows: tuple[PointsRow, ...]


@dataclass(frozen=True)
class MilestoneRow:
    points: int
    prize: str
    reached: bool


@dataclass(frozen=True)
class EventCard:
    """`title`: the game's, else Plarium's name, which `plarium_name` always is (its extras,
    "+ 40 Soul Tokens"); `points_name`: what the game calls its points; `when`: how long it has
    left, until it starts or to claim its prizes ("1d 4h", "starts in 9h", "13h to claim");
    `fusion`: the champion it's part of a fusion for; `points`/`position` None when the account
    has no standing; `to_next`: points short of the next milestone."""

    id: int
    title: str
    plarium_name: str
    points_name: str
    kind: str
    tournament: bool
    fusion: str | None
    when: str
    points: int | None
    position: int | None
    rating_size: int | None
    to_next: int | None
    reached: int
    milestones: tuple[MilestoneRow, ...]
    points_tables: tuple[PointsTable, ...]
    turn_scored: bool  # some of its points go by how few turns a fight takes
    highlights: tuple[str, ...]
    max_points_per_day: int | None
    summons: SummonPlan | None  # the shards reaching each milestone takes, when it scores them
    brews: BrewPlan | None  # what brewing a champion earns, when it scores level-ups
    fights: FightPlan | None  # what a dungeon run earns, when it scores its turns or its gear
    upgrades: UpgradePlan | None  # what upgrading a piece earns, when it scores upgrades


@dataclass(frozen=True)
class EventsPage:
    """`levels`: the account's level as its brackets tell ("level 100"), if they do;
    `read_ago`: how old the points are ("2 min ago")."""

    running: tuple[EventCard, ...]  # soonest to end first
    upcoming: tuple[EventCard, ...]  # soonest to start first
    ended: tuple[EventCard, ...]  # prizes still to claim
    levels: str | None
    read_ago: str


@dataclass(frozen=True)
class Names:
    """What prizes and rules are shown by: champions by type id, black market items by id,
    sets by kind, relics by type id."""

    heroes: dict[int, str]
    items: dict[str, str]
    sets: dict[str, str]
    relics: dict[int, str]

    def hero(self, hero_type_id: int) -> str:
        return self.heroes.get(hero_type_id) or f"Champion {hero_type_id}"

    def item(self, key: str) -> str:
        return self.items.get(key) or words(key)


def events_page(
    account: Account,
    events: Events,
    relic_names: dict[int, str],
    summoning: Summoning | None,
    levelling: Levelling,
    loot: Loot,
    now: datetime,
    read_ago: str,
) -> EventsPage:
    """`summoning`: what the shard plans need (None if the reader found no summons)."""
    levels = account_levels(events)
    heroes = {type_id: hero.name for type_id, hero in account.tables.hero_types.items()}
    names = Names(heroes, events.item_names, events.set_names, relic_names)

    def cards(selected: Sequence[GameEvent]) -> tuple[EventCard, ...]:
        return tuple(
            event_card(
                event,
                events.standings.get(event.prototype_id),
                levels,
                names,
                summoning,
                levelling,
                loot,
                now,
            )
            for event in selected
        )

    running = [e for e in events.events if e.start <= now < e.end]
    upcoming = [e for e in events.events if now < e.start]
    ended = [e for e in events.events if e.end <= now and e.claim_by and now < e.claim_by]

    return EventsPage(
        running=cards(sorted(running, key=lambda e: e.end)),
        upcoming=cards(sorted(upcoming, key=lambda e: e.start)),
        ended=cards(sorted(ended, key=lambda e: e.end)),
        levels=levels_text(levels),
        read_ago=read_ago,
    )


def event_card(
    event: GameEvent,
    standing: Standing | None,
    levels: tuple[int, int] | None,
    names: Names,
    summoning: Summoning | None,
    levelling: Levelling,
    loot: Loot,
    now: datetime,
) -> EventCard:
    milestones = milestones_for(event, standing, levels)
    points = standing.points if standing else None
    rows = milestone_rows(milestones, points or 0, names)
    ahead = [m.points for m in milestones if m.points > (points or 0)]
    fusion = FUSION.match(event.name)

    return EventCard(
        id=event.id,
        title=event.texts.title or event_name(event.name),
        plarium_name=event.name,
        points_name=event.texts.points_name or "Points",
        kind=kind_label(event),
        tournament=event.tournament,
        fusion=names.hero(int(fusion.group(1))) if fusion else None,
        when=when_text(event, now),
        points=points,
        position=standing.position if standing else None,
        rating_size=event.rating_size,
        to_next=ahead[0] - (points or 0) if ahead else None,
        reached=sum(row.reached for row in rows),
        milestones=rows,
        points_tables=points_tables(event.rules, names),
        turn_scored=any(isinstance(rule.points, TurnPoints) for rule in event.rules),
        highlights=tuple(text for prize in event.highlights if (text := prize_text(prize, names))),
        max_points_per_day=event.max_points_per_day,
        summons=(
            None
            if summoning is None
            else summon_plan(event, points or 0, milestones, summoning, now)
        ),
        brews=brew_plan(event, levelling),
        fights=fight_plan(event, loot),
        upgrades=upgrade_plan(event),
    )


def milestone_rows(
    milestones: tuple[Milestone, ...], points: int, names: Names
) -> tuple[MilestoneRow, ...]:
    return tuple(
        MilestoneRow(m.points, prize_text(m.prize, names), points >= m.points) for m in milestones
    )


def points_tables(rules: tuple[Rule, ...], names: Names) -> tuple[PointsTable, ...]:
    """A table per action and the fields its rules set, in the game's order."""
    groups: dict[tuple[str, tuple[str, ...]], list[tuple[dict[str, str], Rule]]] = {}

    for rule in rules:
        labels = condition_labels(rule.conditions, names)
        groups.setdefault((rule.action, tuple(sorted(labels))), []).append((labels, rule))

    tables = (points_table(action, group) for (action, _), group in groups.items())
    return tuple(table for table in tables if table.rows)


def points_table(action: str, group: list[tuple[dict[str, str], Rule]]) -> PointsTable:
    """The group's rules as rows, or a grid when they vary along two fields."""
    fields = list(group[0][0])
    values = {f: list(dict.fromkeys(labels[f] for labels, _ in group)) for f in fields}
    shared = [f for f in fields if len(values[f]) == 1]
    varying = sorted((f for f in fields if f not in shared), key=lambda f: -len(values[f]))
    note = " · ".join(values[f][0] for f in shared)
    label = ACTIONS.get(action) or words(action)

    match varying:
        case [side, across]:
            cells = {(labels[side], labels[across]): points_text(r.points) for labels, r in group}
            rows = (
                PointsRow(row, tuple(cells.get((row, column), "") for column in values[across]))
                for row in values[side]
            )
            columns = tuple(values[across])

        case _:
            rows = (
                PointsRow(row_label(labels, varying), (points_text(rule.points),))
                for labels, rule in group
            )
            side, columns = " · ".join(varying), ("Points",)

    earning = tuple(row for row in rows if any(cell not in ("", "0") for cell in row.cells))
    return PointsTable(label, note, side, columns, earning)


def row_label(labels: dict[str, str], varying: list[str]) -> str:
    return " · ".join(labels[name] for name in varying) or "Each"


def condition_labels(conditions: tuple[Condition, ...], names: Names) -> dict[str, str]:
    """A rule's conditions as heading → value, in the game's order (a dungeon's stage
    fields as one: "Stages 1–3")."""
    labels: dict[str, str] = {}
    stages = {c.field: c.value for c in conditions if c.field in STAGE_FIELDS}

    for condition in conditions:
        match condition:
            case Condition(field=stage_field) if stage_field in STAGE_FIELDS:
                labels["Stages"] = stages_text(stages)

            case Condition(field="Rank", value=str(rank)):
                labels["Rank"] = f"{RANKS.get(rank, rank)}★"

            case Condition(field="Grade", value=str(grade)):
                labels["Stars"] = f"{grade.removeprefix('Stars')}★"

            case Condition(field="Level", value=int(level)):
                labels["Level"] = f"+{level}"

            case Condition(field="Elements", value=tuple(elements)):
                labels["Affinity"] = " / ".join(elements)

            case Condition(field="SoulStoneTypeId" | "BlackMarketItemId", value=str(item)):
                labels["Item"] = names.item(item)

            case Condition(field=other, value=value):
                labels[words(other.removesuffix("Id"))] = words(str(value))

    return labels


def points_text(points: int | TurnPoints) -> str:
    match points:
        case TurnPoints(least=least, most=most):
            return f"{least}–{most}"

    return f"{points:,}"


def prize_text(prize: Prize, names: Names) -> str:
    return ", ".join(prize_item_text(item, names) for item in prize)


def prize_item_text(item: PrizeItem, names: Names) -> str:
    match item:
        case Goods(key=key, count=count, resource=True):
            return f"{count:,} {RESOURCES.get(key) or names.item(key)}"

        case Goods(key=key, count=count):
            return f"{count:,} × {names.item(key)}"

        case Fragments(hero_type_id=hero, count=count):
            return f"{count} {names.hero(hero)} fragments"

        case Soul(hero_type_id=hero, rarity=rarity, grade=grade):
            return f"{names.hero(hero)}'s soul ({grade.removeprefix('Stars')}★ {rarity})"

        case Pieces(count=count, set_kind=set_kind, rank=rank, rarity=rarity):
            set_name = names.sets.get(set_kind) or words(set_kind)
            return f"{count} {RANKS.get(rank, rank)}★ {rarity} {set_name} pieces"

        case RelicPrize(type_id=type_id, rank=rank):
            return f"{names.relics.get(type_id, 'Relic')} ({words(rank)})"

        case RelicStones(count=count, rarities=rarities):
            return f"{count} × {' / '.join(rarities)} relic stone"

        case Other(kind=kind, count=count):
            return f"{count} × {words(kind).lower().removesuffix('s')}"

    assert_never(item)


def when_text(event: GameEvent, now: datetime) -> str:
    if now < event.start:
        return f"starts in {span_text(event.start - now)}"

    if now < event.end:
        return span_text(event.end - now)

    if event.claim_by and now < event.claim_by:
        return f"{span_text(event.claim_by - now)} to claim"

    return "ended"


def levels_text(levels: tuple[int, int] | None) -> str | None:
    match levels:
        case (low, high) if low == high:
            return f"level {low}"

        case (low, high):
            return f"levels {low}–{high}"

    return None


def event_name(name: str) -> str:
    """Plarium's name without the fusion it's for and its start date, which the card shows."""
    return NAME_DATE.sub("", FUSION.sub("", name)).strip(" ,")


def kind_label(event: GameEvent) -> str:
    if event.tournament:
        return f"Tournament · {TOURNAMENT_KINDS.get(event.kind) or words(event.kind)}"

    return SOLO_KINDS.get(event.kind) or words(event.kind)


def words(name: str) -> str:
    """The game's identifier as words: "IceGolemCave" → "Ice Golem Cave", "GoldIV" → "Gold IV"."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|_", " ", name)
    return re.sub(r"\s+", " ", spaced).strip()
