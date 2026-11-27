"""
events.py - the events and tournaments on in the game, and the account's points in each, from
the reader's events file (`paths.EVENTS`: the game's own JSON for them, `UpdatableGlobalEventsData`,
and each event's quest's progress). The JSON's short keys are named by `paths.EVENTS_SCHEMA`
(`tools.gen_schema` over the dump's `[Json]` attributes), as the static data's are by its
schema. Its title and points' name are ids into the texts the server sends in
the player's language, which the reader keeps beside it.

An event is a solo one (points for actions, prizes at milestones) or a tournament (the same,
ranked against a bracket of players). Milestones can depend on the account's level: then each
bracket of levels has its own, and the account's bracket is the one its standing names, else
the one holding the level the other events' brackets agree on (`account_levels`).

- `Condition`, `TurnPoints`, `Rule`: what earns points (`TurnPoints`: a dungeon fight scored by
  how few turns it takes)
- `Goods`, `Fragments`, `Soul`, `Pieces`, `RelicPrize`, `RelicStones`, `Other`, `Prize`: what a
  milestone or place gives
- `Milestone`, `Bracket`, `EventTexts`, `GameEvent`, `Standing`, `Events`: the events, the
  account's place in each, and the item and set names prizes are shown with
- `load_events`: the loader (None when the reader found no events)
- `account_levels`, `bracket_for`, `milestones_for`: the account's bracket and its milestones
- `rule_points`, `holds`: what an action earns for something, by the rules whose conditions
  hold for it (the event plans' one way of reading the rules)
- `decode`, `parse_event`, `parse_texts`, `parse_rule`, `parse_milestones`, `parse_prize`,
  `parse_standing`, `event_end`, `moment`: its steps
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import orjson

TOURNAMENT = "CommonTournament"  # an event's quest category, when it's a tournament
POINTS = "Points"  # a rule's field: what it earns
TURN_SCORED = "TurnAttackParameters"  # a rule's field: earned by how few turns a fight takes
TICKS_PER_SECOND = 10_000_000  # a TimeSpan's, as the game's JSON gives durations


@dataclass(frozen=True)
class Condition:
    """What a rule holds an action to: `subject` the kind of thing ("Artifact", "Hero",
    "Dungeon"), `field` its property ("Rank"), `value` the game's ("Five"; several for a
    list, as `Elements`)."""

    subject: str
    field: str
    value: str | int | float | tuple[str, ...]


@dataclass(frozen=True)
class TurnPoints:
    """A fight scored by its turns: round(`scale` × `x` × turns^`y`), `y` below 0 so the fewer
    the more, held between `least` and `most`. The server scores it, so this is read off fights:
    Sand Devil 25 (scale 30), 44 turns for 43 points and 22 for 48."""

    least: int
    most: int
    x: float
    y: float
    scale: float

    def points(self, turns: int) -> int:
        earned = round(self.scale * self.x * max(turns, 1) ** self.y)
        return min(max(earned, self.least), self.most)


@dataclass(frozen=True)
class Rule:
    """An action ("Artifact_Collect", the game's) under some conditions, and what it earns."""

    action: str
    conditions: tuple[Condition, ...]
    points: int | TurnPoints


@dataclass(frozen=True)
class Goods:
    """Black market items (by id: "SkillUpgradeItemRare") or resources ("Silver")."""

    key: str
    count: int
    resource: bool


@dataclass(frozen=True)
class Fragments:
    hero_type_id: int
    count: int


@dataclass(frozen=True)
class Soul:
    """A champion's soul (Double Ascension)."""

    hero_type_id: int
    rarity: str
    grade: str


@dataclass(frozen=True)
class Pieces:
    """Gear of one set, rank and rarity."""

    count: int
    set_kind: str
    rank: str
    rarity: str


@dataclass(frozen=True)
class RelicPrize:
    type_id: int
    rank: str


@dataclass(frozen=True)
class RelicStones:
    count: int
    rarities: tuple[str, ...]


@dataclass(frozen=True)
class Other:
    """A prize the page only names: avatars, skins, chests."""

    kind: str
    count: int


type PrizeItem = Goods | Fragments | Soul | Pieces | RelicPrize | RelicStones | Other
type Prize = tuple[PrizeItem, ...]


@dataclass(frozen=True)
class Milestone:
    points: int
    prize: Prize


@dataclass(frozen=True)
class Bracket:
    """The players an event ranks the account against, by level, with their own milestones
    (none in a teaser: the game loads them when it starts)."""

    min_level: int
    max_level: int
    milestones: tuple[Milestone, ...]


@dataclass(frozen=True)
class EventTexts:
    """What the game shows an event by, in its language: each None if the server sent no
    text for it (a teaser's may come later)."""

    title: str | None
    points_name: str | None  # "Fate Points"; the game's default is "Points"


@dataclass(frozen=True)
class GameEvent:
    """`prototype_id`: its quest's, which the account's standing is kept by; `name` is
    Plarium's own ("Fuse 10910 Ice Golem (3d), 26-11-2026"), `texts` the game's; `kind` the
    game's (a solo event's type, "PointBased", or a tournament's, "IceGolem"); `milestones`
    unless they're per bracket; `highlights`: the prizes it leads with; `rating_size`: how
    many players a tournament ranks."""

    id: int
    prototype_id: int
    name: str
    texts: EventTexts
    tournament: bool
    kind: str
    teaser: datetime | None
    start: datetime
    end: datetime
    claim_by: datetime | None
    rules: tuple[Rule, ...]
    milestones: tuple[Milestone, ...]
    brackets: tuple[Bracket, ...]
    highlights: tuple[Prize, ...]
    max_points_per_day: int | None
    rating_size: int | None


@dataclass(frozen=True)
class Standing:
    """The account's place in an event, as the game last held it: a tournament's position
    only once the server has sent it; `bracket` an index into the event's brackets."""

    points: int
    position: int | None
    bracket: int | None


@dataclass(frozen=True)
class Events:
    """`standings` by an event's `prototype_id`; the names prizes are shown with:
    `item_names` by black market item id, `set_names` by set kind ("GetExtraTurn")."""

    events: tuple[GameEvent, ...]
    standings: dict[int, Standing]
    item_names: dict[str, str] = field(default_factory=dict)
    set_names: dict[str, str] = field(default_factory=dict)


def load_events(events: Path, schema: Path, game: Path) -> Events | None:
    """The reader's events, named by `schema`, with `game`'s item and set names (None when
    it found none, or hasn't run)."""
    raw = orjson.loads(events.read_bytes()) if events.exists() else None

    if not raw:
        return None

    tables = orjson.loads(schema.read_bytes())
    texts = {int(text_id): text for text_id, text in raw.get("texts", {}).items()}
    data = decode(orjson.loads(raw["json"]), "UpdatableGlobalEventsData", tables)
    items = game / "items.json"
    sets = orjson.loads((game / "sets.json").read_bytes())

    return Events(
        events=tuple(parse_event(event, tables, texts) for event in data["Events"]),
        standings={p["prototype_id"]: parse_standing(p) for p in raw["progress"]},
        item_names=orjson.loads(items.read_bytes()) if items.exists() else {},
        set_names={s["id"]: s["name"] for s in sets},
    )


def account_levels(events: Events) -> tuple[int, int] | None:
    """The account's level as far as its brackets tell: the range every bracket it's in
    holds (None if it's in none, or they disagree)."""
    ranges = [
        (bracket.min_level, bracket.max_level)
        for event in events.events
        if (bracket := bracket_for(event, events.standings.get(event.prototype_id), None))
    ]

    if not ranges:
        return None

    low = max(low for low, _ in ranges)
    high = min(high for _, high in ranges)
    return (low, high) if low <= high else None


def bracket_for(
    event: GameEvent, standing: Standing | None, levels: tuple[int, int] | None
) -> Bracket | None:
    """The account's bracket: the one its standing names, else the one holding its levels."""
    match standing, levels:
        case Standing(bracket=int(index)), _ if index < len(event.brackets):
            return event.brackets[index]

        case _, (low, high):
            return next(
                (b for b in event.brackets if b.min_level <= low and high <= b.max_level), None
            )

    return None


def milestones_for(
    event: GameEvent, standing: Standing | None, levels: tuple[int, int] | None
) -> tuple[Milestone, ...]:
    """The milestones the account plays for: its bracket's, else the event's own."""
    if bracket := bracket_for(event, standing, levels):
        return bracket.milestones or event.milestones

    return event.milestones


def rule_points(rules: tuple[Rule, ...], action: str, facts: Mapping[str, object]) -> int:
    """What an action earns for something with these facts (`{"Grade": "Stars3"}`): every rule
    for it whose conditions all hold adds its points, as the game adds a piece's rank and rarity
    (a rule scored by turns adds none)."""
    return sum(
        rule.points
        for rule in rules
        if rule.action == action
        and isinstance(rule.points, int)
        and all(holds(condition, facts) for condition in rule.conditions)
    )


def holds(condition: Condition, facts: Mapping[str, object]) -> bool:
    """Whether a condition holds for these facts: its value, one of its values (affinities), or
    a stage range (`MinNumber`/`MaxNumber` against `Number`). One on a fact not given fails:
    a rule this can't check doesn't count."""
    match condition:
        case Condition(field="MinNumber", value=int(low)):
            return isinstance(number := facts.get("Number"), int) and number >= low

        case Condition(field="MaxNumber", value=int(high)):
            return isinstance(number := facts.get("Number"), int) and number <= high

        case Condition(field=name, value=tuple(values)):
            return name in facts and facts[name] in values

        case Condition(field=name, value=value):
            return name in facts and facts[name] == value

    return False


def parse_event(raw: dict, schema: dict, texts: dict[int, str]) -> GameEvent:
    """The event, its texts looked up by the ids its interface settings name."""
    quest = raw["QuestData"]["Quest"]
    info = quest.get("GlobalEventInfo") or {}
    dates = raw["DateCondition"]
    reward = info.get("Reward") or {}
    tournament = quest["CategoryId"] == TOURNAMENT

    return GameEvent(
        id=raw["Id"],
        prototype_id=quest["PrototypeId"],
        name=quest.get("Name") or f"Event {raw['Id']}",
        texts=parse_texts(raw.get("InterfaceSettingsJson"), schema, texts),
        tournament=tournament,
        kind=(info.get("TournamentKindId") if tournament else info.get("GlobalEventSoloTypeId"))
        or quest["CategoryId"],
        teaser=maybe_moment(dates.get("TeaserStart")),
        start=moment(dates["Start"]),
        end=event_end(dates),
        claim_by=maybe_moment(dates.get("TakePrizeDeadline")),
        rules=tuple(
            parse_rule(action, rule)
            for action, rules in (info.get("Rules") or {}).items()
            for rule in rules
        ),
        milestones=parse_milestones(reward.get("ProgressionReward")),
        brackets=tuple(
            Bracket(
                bracket.get("MinLevel") or 1,
                bracket.get("MaxLevel") or 100,
                parse_milestones(bracket.get("ProgressionReward")),
            )
            for bracket in info.get("Brackets") or ()
        ),
        highlights=tuple(parse_prize(prize) for prize in reward.get("TopRewards") or ()),
        max_points_per_day=info.get("MaxPointsPerDay") or None,
        rating_size=info.get("GlobalRatingSize") if tournament else None,
    )


def parse_texts(settings_json: str | None, schema: dict, texts: dict[int, str]) -> EventTexts:
    """The texts the event's settings (JSON within its JSON) name."""
    raw = orjson.loads(settings_json) if settings_json else {}
    settings = decode(raw, "GlobalEventInterfaceSettingsDto", schema) or {}

    def text(field: str) -> str | None:
        return texts.get(settings[field]) if field in settings else None

    return EventTexts(text("TitleId"), text("PointsNameId"))


def parse_rule(action: str, raw: dict) -> Rule:
    """A rule: its subjects' set fields are its conditions."""
    conditions = tuple(
        Condition(subject, name, tuple(value) if isinstance(value, list) else value)
        for subject, fields in raw.items()
        if isinstance(fields, dict) and subject != TURN_SCORED
        for name, value in fields.items()
        if value not in (None, 0, False, "", [])
    )

    match raw.get(TURN_SCORED):
        case {"MinPoints": int(least), "MaxPoints": int(most), "X": x, "Y": y, "S": scale}:
            points: int | TurnPoints = TurnPoints(least, most, float(x), float(y), float(scale))

        case _:
            points = raw.get(POINTS) or 0

    return Rule(action, conditions, points)


def parse_milestones(raw: list[dict] | None) -> tuple[Milestone, ...]:
    milestones = (Milestone(item["Points"], parse_prize(item.get("Prize"))) for item in raw or ())
    return tuple(sorted(milestones, key=lambda m: m.points))


def parse_prize(raw: dict | None) -> Prize:
    """A prize's parts: the game's `UserPrize`, its empty fields left out."""
    prize = raw or {}
    resources = (prize.get("Resources") or {}).get("RawValues") or {}
    pieces = Counter(
        (piece["SetKindId"], piece["RankId"], piece["RarityId"])
        for piece in prize.get("Artifacts") or ()
    )
    others = (
        Other(kind, len(values))
        for kind, values in prize.items()
        if kind in ("Avatars", "HeroSkins", "RandomChests") and values
    )

    return (
        *(Goods(key, count, resource=True) for key, count in resources.items() if count),
        *(Goods(key, count, False) for key, count in (prize.get("BlackMarketItems") or {}).items()),
        *(Fragments(int(hero), count) for hero, count in (prize.get("HeroParts") or {}).items()),
        *(
            Soul(soul["BaseHeroTypeId"], soul["Rarity"], soul["Grade"])
            for soul in prize.get("HeroSouls") or ()
        ),
        *(Pieces(count, *kind) for kind, count in pieces.items()),
        *(RelicPrize(relic["TypeId"], relic["Rank"]) for relic in prize.get("Relics") or ()),
        *(
            RelicStones(stones["Count"], tuple(stones.get("Rarities") or ()))
            for stones in prize.get("RandomRelicStonesPrizes") or ()
        ),
        *others,
    )


def parse_standing(raw: dict) -> Standing:
    return Standing(raw["points"], raw["position"], raw["bracket"])


def moment(milliseconds: int) -> datetime:
    """A time in the game's JSON (Unix milliseconds), in UTC."""
    return datetime.fromtimestamp(milliseconds / 1000, UTC)


def event_end(dates: dict) -> datetime:
    """When it stops scoring, as the game's timer shows it: its `End`, but a tournament's
    `BracketDuration` from its start, a day past its `End`, and points count all the way (seen
    in game). The client's own state reads `End` as where a tournament starts rewarding, for
    `RewardDuration` (a day): that lands on the same time today, and the timer itself is the
    tournaments web view's, so which the server goes by isn't known."""
    match dates.get("BracketDuration"):
        case int(ticks):
            return moment(dates["Start"]) + timedelta(seconds=ticks / TICKS_PER_SECOND)

        case _:
            return moment(dates["End"])


def maybe_moment(milliseconds: int | None) -> datetime | None:
    return None if milliseconds is None else moment(milliseconds)


def decode(value: Any, type_name: str, schema: dict) -> Any:
    """`value` as the C# type `type_name`: classes' short keys named, enums by name, a text key
    by its default text; what the schema doesn't know is kept as it is."""
    type_name = type_name.removesuffix("?")
    classes, enums = schema["classes"], schema["enums"]

    match type_name:
        case _ if value is None:
            return None

        case _ if type_name.startswith("Nullable<"):
            return decode(value, type_name[len("Nullable<") : -1], schema)

        case _ if type_name.endswith("[]") and isinstance(value, list):
            return [decode(item, type_name[:-2], schema) for item in value]

        case _ if type_name.startswith("List<") and isinstance(value, list):
            return [decode(item, type_name[len("List<") : -1], schema) for item in value]

        case _ if type_name.startswith("Dictionary<") and isinstance(value, dict):
            key_type, value_type = type_arguments(type_name)
            return {
                decode_key(key, key_type, enums): decode(item, value_type, schema)
                for key, item in value.items()
            }

        case "SharedLTextKey" if isinstance(value, dict):
            return value.get("d")

        case _ if (short := type_name.split(".")[-1]) in enums:
            return enums[short].get(str(value), value)

        case _ if short in classes and isinstance(value, dict):
            fields = classes[short]
            return {
                fields[key]["name"]: decode(item, fields[key]["type"], schema)
                for key, item in value.items()
                if key in fields
            }

    return value


def decode_key(key: str, type_name: str, enums: dict) -> str:
    """A dictionary's key: an enum's by name, any other as the text it came as."""
    short = type_name.split(".")[-1]
    return enums[short].get(key, key) if short in enums else key


def type_arguments(generic: str) -> tuple[str, str]:
    """A two-argument generic's arguments: `Dictionary<int, List<int>>` → int, List<int>."""
    inner = generic[generic.index("<") + 1 : -1]
    depth = 0

    for index, char in enumerate(inner):
        depth += {"<": 1, ">": -1}.get(char, 0)

        if char == "," and depth == 0:
            return inner[:index].strip(), inner[index + 1 :].strip()

    raise ValueError(f"not a two-argument generic: {generic}")
