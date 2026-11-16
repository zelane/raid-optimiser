"""
team.py - a team finder's views, shared by the pages that find teams: the team's slots (the
user's champions and the search's), what every team must bring (wanted tags, grouped by side),
the gear, relics and assumptions it may count on, and each need as the team meets it.

- `ChoiceView`, `RelicOption`, `SlotView`, `IconView`, `Contributor`, `NeedView`, `WantView`,
  `WantGroup`, `CountView`, `GearView`, `GearGroup`, `AssumedView`, `TeamView`: the views
- `Note`, `no_note`: what a page says about a tag on offer
- `Query`, `PageUrl`, `TeamLinks`, `listing`: a team page's URLs from its state (the state is
  all in the URL)
- `team_view`: the team's panels
- `slot_worn`, `worn_now`, `relic_value`, `relic_options`, `best_copies`, `relic_label`: each
  slot's relics, and what it can pick from
- `slot_view`, `need_view`, `WANT_GROUPS`, `want_groups`, `want_view`, `count_view`, `gear_groups`,
  `gear_view`, `assumed_views`, `assumed_view`, `percent`: its pieces
- `ICON_NAMES`, `icon_view`, `icon_url`, `icon_name`: the game's icons for buffs, debuffs and
  effects
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode

from optimiser.account import Account, Champion, Relic, faction_label
from optimiser.teams.cover import Member, NeedCover
from optimiser.teams.find import Worn
from optimiser.teams.gear import Assumed, Gear, Loadout, worn_relic
from optimiser.teams.needs import Distinct
from optimiser.teams.tags import Side, Tag, plain_label
from webui.forms.team import Offers, RelicChoice, SlotPick, TeamAsk, Unmatched
from webui.service.views import ChampionRow, asset_url, champion_row, choice_label

type Note = Callable[[Tag], str | None]
type Query = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ChoiceView:
    """A champion as the slot picker lists it: "Name, 6★ L60 #id" (the form reads the id)."""

    label: str


@dataclass(frozen=True)
class RelicOption:
    """A relic a slot's champion can wear: the `relic` field's value ("" what they wear now,
    "none", a relic's id), in words, and whether it's the one picked."""

    value: str
    label: str
    selected: bool


@dataclass(frozen=True)
class SlotView:
    """A team slot: its champion (None when open), as the picker shows it, and whether the
    search suggested it (else the user chose it) and the team needs it. `problem`: why the
    text typed in it isn't a champion (the slot stays open, the text kept). `relic`: its
    `relic` field's value, `relics` what it can pick (a champion's slot only)."""

    champion: ChampionRow | None
    choice: str  # the picker's text; "" when open
    suggested: bool
    needed: bool
    problem: str | None = None
    relic: str = ""
    relics: list[RelicOption] = field(default_factory=list)


@dataclass(frozen=True)
class IconView:
    """A buff, debuff or effect as an icon: the game's art, or None (the page draws a glyph)."""

    label: str
    url: str | None


@dataclass(frozen=True)
class Contributor:
    """A champion bringing a need, and how far its best source can be counted on."""

    champion: ChampionRow
    score: int  # %
    detail: str  # "2 turns, every 3 turns, 75% chance"


@dataclass(frozen=True)
class NeedView:
    """A need: who on the team brings it, `asks` (what would do), `brought` (for a count, the
    effects the team brings), `notes` (gear that meets it) and its `score` (%)."""

    label: str
    met: bool
    contributors: list[Contributor]
    notes: list[str]
    asks: list[IconView]
    brought: list[IconView]
    score: int


@dataclass(frozen=True)
class WantView:
    """Something the user can ask every team to bring, and whether they have; `note`: where
    it only lands, as the page says (Fear: "Ram form only" on the Chimera page)."""

    key: str  # `Tag.key`
    label: str
    wanted: bool
    note: str | None
    icon_url: str | None


@dataclass(frozen=True)
class WantGroup:
    """The debuffs, the buffs or the effects on offer; `chosen`: how many are wanted."""

    title: str
    wants: list[WantView]
    chosen: int


@dataclass(frozen=True)
class GearView:
    """A set or relic the user can let any champion wear, what it brings, and whether they
    have; `faction`: only a champion of it gets the relic's skill (as the game names it)."""

    key: str
    name: str
    faction: str | None
    on: bool
    brings: list[IconView]


@dataclass(frozen=True)
class GearGroup:
    title: str
    gear: list[GearView]
    chosen: int


@dataclass(frozen=True)
class AssumedView:
    """Something assumed: for the team (`champion` None) or one champion. `key` is how the
    page's URL names it."""

    key: str
    label: str
    champion: str | None
    icon: IconView


@dataclass(frozen=True)
class CountView:
    """So many different debuffs or buffs every team must bring: `field` is the query's
    value ("debuff:3"), `key` what a chip's removal names ("count:debuff:3")."""

    field: str
    key: str
    label: str


@dataclass(frozen=True)
class TeamView:
    """The team's panels: its slots, every champion the slot picker lists (by name), what
    every team must bring (`wants` on offer, `wanted` the chosen ones, in that order; `counts`:
    so many different debuffs or buffs), and the gear on offer (`gear`), allowed (`gear_on`)
    and assumed."""

    slots: list[SlotView]
    choices: list[ChoiceView]
    wants: list[WantGroup]
    wanted: list[WantView]
    counts: list[CountView]
    gear: list[GearGroup]
    gear_on: list[GearView]
    assumed: list[AssumedView]


@dataclass(frozen=True)
class TeamLinks:
    """A team page's own links: its state as its form would send it (`current`, no search: a
    change starts from it), every slot open (`empty`), without each chip (`without`, by the
    chip's key: a wanted tag, a count, gear, an assumption), and listing more options (`more`;
    None when there are no more)."""

    current: str
    empty: str
    without: dict[str, str]
    more: str | None


@dataclass(frozen=True)
class PageUrl:
    """A team page's URL: its `path`, its own fields (`base`: the column, the base needs, the
    grade searched from) and the team's (gear, assumptions, wants, counts, slots)."""

    path: str
    base: Query
    team: TeamView

    def to(self, slots: list[SlotView], extra: Query = (), without: str = "") -> str:
        """The page with these slots, `extra` added and the chip keyed `without` left out."""
        team = self.team
        pairs = [*self.base, ("gear_set", "true")]
        pairs += [("gear", g.key) for g in team.gear_on if g.key != without]
        pairs += [("assume", a.key) for a in team.assumed if a.key != without]
        pairs += [("want", w.key) for w in team.wanted if w.key != without]
        pairs += [("count", c.field) for c in team.counts if c.key != without]

        for slot in slots:
            pairs += [("slot", slot.choice), ("relic", slot.relic)]

        return f"{self.path}?{urlencode(pairs + list(extra))}"

    def links(self, ran: bool, more: Query | None) -> TeamLinks:
        """`ran`: a search ran (a chip's removal runs it again); `more`: what lists more."""
        team = self.team
        keep: Query = (("run", "true"),) if ran else ()
        keys = [w.key for w in team.wanted] + [c.key for c in team.counts]
        keys += [g.key for g in team.gear_on] + [a.key for a in team.assumed]
        return TeamLinks(
            current=self.to(team.slots),
            empty=self.to([]),
            without={key: self.to(team.slots, keep, key) for key in keys},
            more=self.to(team.slots, more) if more else None,
        )


def listing(listed: int, option: int) -> Query:
    """A search's run listing `listed` options, `option` the one shown."""
    return (("run", "true"), ("listed", str(listed)), ("option", str(option)))


def no_note(tag: Tag) -> None:
    return None


def team_view(
    account: Account,
    members: tuple[Member | None, ...],
    ask: TeamAsk,
    offers: Offers,
    enemy: str,
    note: Note = no_note,
) -> TeamView:
    """The panels for the slots as `members` (the lineup's) and as typed (`ask.picks`), the
    wanted debuffs' group naming `enemy`, `note` saying where a tag only lands."""
    allowed = {g.key for g in ask.loadout.gear}
    champions = sorted(account.champions.values(), key=lambda c: (c.name, -c.grade, -c.level))
    choices = ask.relics + (None,) * (len(members) - len(ask.relics))
    slots = []

    for member, pick, choice in zip(members, ask.picks, choices, strict=True):
        view = slot_view(member, pick)

        if member is not None and member.chosen:
            value = relic_value(choice)
            options = relic_options(account, offers, member.champion, choice)
            view = replace(view, relic=value, relics=options)

        slots.append(view)

    return TeamView(
        slots=slots,
        choices=[ChoiceView(choice_label(c)) for c in champions],
        wants=want_groups(offers.tags, ask.wanted, enemy, note),
        wanted=[want_view(tag, True, note) for tag in ask.wanted],
        counts=[count_view(count) for count in ask.counts],
        gear=gear_groups(offers.gear, allowed),
        gear_on=[gear_view(g, True) for g in offers.gear if g.key in allowed],
        assumed=assumed_views(ask.loadout),
    )


def slot_view(member: Member | None, pick: SlotPick) -> SlotView:
    if member is None and isinstance(pick, Unmatched):
        return SlotView(None, pick.text, suggested=False, needed=False, problem=pick.reason)

    if member is None:
        return SlotView(None, "", suggested=False, needed=False)

    return SlotView(
        champion_row(member.champion),
        choice_label(member.champion),
        suggested=not member.chosen,
        needed=member.needed,
    )


def slot_worn(
    account: Account, ask: TeamAsk, offers: Offers, slots: tuple[Champion | None, ...]
) -> Worn:
    """Each slot's relics as its champion wears them (`worn_relic`): the ones picked, else
    what they wear now."""
    sources = {source.id: source for source in offers.relics}
    choices = ask.relics + (None,) * (len(slots) - len(ask.relics))
    worn = []

    for champion, choice in zip(slots, choices, strict=True):
        relics = worn_now(account, champion) if choice is None else choice
        worn.append(
            tuple(
                worn_relic(account, relic, sources[relic.type_id], champion)
                for relic in relics
                if champion and relic.type_id in sources
            )
        )

    return tuple(worn)


def worn_now(account: Account, champion: Champion | None) -> tuple[Relic, ...]:
    if champion is None:
        return ()

    ids = account.worn_relics.get(champion.id, ())
    return tuple(account.relic_items[i] for i in ids if i in account.relic_items)


def relic_value(choice: RelicChoice) -> str:
    match choice:
        case None:
            return ""
        case ():
            return "none"
        case (relic, *_):
            return str(relic.id)


def relic_options(
    account: Account, offers: Offers, champion: Champion, choice: RelicChoice
) -> list[RelicOption]:
    """What the slot's champion wears now, no relic, then the best copy of each relic the
    account has (and the one picked, if it isn't one), by name."""
    names = {source.id: source.name for source in offers.relics}
    picked = relic_value(choice)
    now = [relic_label(r, names) for r in worn_now(account, champion)]
    options = [
        RelicOption("", f"Worn: {', '.join(now) or 'none'}", picked == ""),
        RelicOption("none", "No relic", picked == "none"),
    ]
    copies = best_copies(account)

    if choice:
        copies = {**copies, choice[0].type_id: choice[0]}

    for relic in sorted(copies.values(), key=lambda r: names.get(r.type_id, "")):
        if relic.type_id in names:
            value = str(relic.id)
            options.append(RelicOption(value, relic_label(relic, names), picked == value))

    return options


def best_copies(account: Account) -> dict[int, Relic]:
    """The highest-level copy of each relic type the account has."""
    best: dict[int, Relic] = {}

    for relic in account.relic_items.values():
        held = best.get(relic.type_id)
        if held is None or relic.level > held.level:
            best[relic.type_id] = relic

    return best


def relic_label(relic: Relic, names: dict[int, str]) -> str:
    return f"{names.get(relic.type_id, f'relic {relic.type_id}')} L{relic.level}"


def count_view(count: Distinct) -> CountView:
    field = f"{count.side}:{count.count}"
    return CountView(field, f"count:{field}", f"{count.count} different {count.side}s")


def gear_groups(offered: list[Gear], allowed: set[str]) -> list[GearGroup]:
    groups = []

    for kind, title in (("set", "Artifact sets"), ("relic", "Relics you own")):
        views = [gear_view(g, g.key in allowed) for g in offered if g.kind == kind]
        groups.append(GearGroup(title, views, sum(v.on for v in views)))

    return groups


def gear_view(gear: Gear, on: bool) -> GearView:
    brings = [icon_view(tag) for tag in gear.tags if tag.side != Side.MECHANIC]
    faction = faction_label(gear.faction) if gear.faction else None
    return GearView(gear.key, gear.name, faction, on, sorted(brings, key=lambda i: i.label))


def assumed_views(loadout: Loadout) -> list[AssumedView]:
    """The team's assumptions (assumed gear) and the single champions'."""
    team = [
        AssumedView(tag.key, plain_label(tag), None, icon_view(tag))
        for gear in loadout.gear
        if gear.kind == "assumed"
        for tag in gear.tags
    ]
    single = [assumed_view(a) for a in loadout.assumed]
    return team + single


def assumed_view(assumed: Assumed) -> AssumedView:
    tag = assumed.tag
    return AssumedView(assumed.key, plain_label(tag), assumed.champion.name, icon_view(tag))


WANT_GROUPS = ((Side.DEBUFF, "Debuffs on {enemy}"), (Side.BUFF, "Buffs"), (Side.EFFECT, "Effects"))


def want_groups(
    offered: list[Tag], wanted: tuple[Tag, ...], enemy: str, note: Note
) -> list[WantGroup]:
    """The tags on offer by side, the debuffs' group naming the enemy ("the Chimera")."""
    groups = []

    for side, title in WANT_GROUPS:
        tags = [tag for tag in offered if tag.side == side]
        views = [want_view(tag, tag in wanted, note) for tag in tags]
        groups.append(WantGroup(title.format(enemy=enemy), views, sum(v.wanted for v in views)))

    return groups


def want_view(tag: Tag, wanted: bool, note: Note) -> WantView:
    return WantView(tag.key, plain_label(tag), wanted, note(tag), icon_url(tag))


# Status kinds whose icon (`statuses/`, the game's sprite names) is named otherwise; the rest
# follow `icon_name`'s rules.
ICON_NAMES = {
    "Burn": "AoEContinuousDamage",
    "SimpleStoneSkin": "StoneSkin",
    "ReflectiveStoneSkin": "StoneSkin",
    "Counterattack": "StatusCounterattack",
    "LesserSeal": "Seal",
    "GreaterSeal": "Seal2",
    "NecrosisSource": "Necrosis",
    "DuelTargetMark": "Duel",
    "ArtifactSet_Shield": "Shield",
    # Skill effects with a status of the same sense.
    "IncreaseStamina": "IncreaseStamina",
    "Revive": "ReviveOnDeath",
    "Heal": "ContinuousHeal",
    "PassiveBlockDebuff": "BlockDebuff",
    "PassiveCounterattack": "StatusCounterattack",
    "PassiveReflectDamage": "ReflectDamage",
    "PassiveUnkillable": "Unkillable",
}
STAT_STATUSES = ("Attack", "Defence", "Speed", "Accuracy", "Resistance", "CriticalChance")
STAT_STATUSES += ("CriticalDamage",)


def icon_url(tag: Tag) -> str | None:
    """The game's icon for a buff, debuff or effect, if it has one."""
    return asset_url("statuses", icon_name(tag))


def icon_name(tag: Tag) -> str:
    """Stat buffs and debuffs are "StatusIncrease…" / "StatusReduce…"."""
    if name := ICON_NAMES.get(tag.name):
        return name

    for prefix, sprite in (("Increase", "StatusIncrease"), ("Decrease", "StatusReduce")):
        stat = tag.name.removeprefix(prefix)
        if tag.name.startswith(prefix) and stat in STAT_STATUSES:
            return sprite + stat

    return tag.name


def need_view(need: NeedCover) -> NeedView:
    contributors = [
        Contributor(champion_row(champion), percent(rating.score), rating.detail)
        for champion, rating in zip(need.by, need.ratings, strict=True)
    ]
    return NeedView(
        label=need.label,
        met=need.met,
        contributors=sorted(contributors, key=lambda c: -c.score),
        notes=list(need.notes),
        score=percent(need.score),
        asks=[icon_view(tag) for tag in need.asks],
        brought=[icon_view(tag) for tag in need.brought],
    )


def percent(score: float) -> int:
    return round(score * 100)


def icon_view(tag: Tag) -> IconView:
    return IconView(plain_label(tag), icon_url(tag))
