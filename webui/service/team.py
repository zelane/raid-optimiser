"""
team.py - a team finder's views, shared by the pages that find teams: the team's slots (the
user's champions and the search's), what every team must bring (wanted tags, grouped by side),
the gear, relics and assumptions it may count on, and each need as the team meets it.

- `ChoiceView`, `SlotView`, `IconView`, `Contributor`, `NeedView`, `WantView`, `WantGroup`,
  `CountView`, `GearView`, `GearGroup`, `AssumedView`, `TeamView`: the views
- `Note`, `no_note`: what a page says about a tag on offer
- `team_view`: the team's panels
- `slot_view`, `need_view`, `WANT_GROUPS`, `want_groups`, `want_view`, `count_view`, `gear_groups`,
  `gear_view`, `assumed_views`, `assumed_view`, `percent`: its pieces
- `ICON_NAMES`, `icon_view`, `icon_url`, `icon_name`: the game's icons for buffs, debuffs and
  effects
"""

from collections.abc import Callable
from dataclasses import dataclass

from optimiser.account import Account
from optimiser.teams.cover import Member, NeedCover
from optimiser.teams.gear import Assumed, Gear, Loadout
from optimiser.teams.needs import Distinct
from optimiser.teams.tags import Side, Tag, plain_label
from webui.forms.team import Offers, SlotPick, TeamAsk, Unmatched
from webui.service.views import ChampionRow, asset_url, champion_row, choice_label

type Note = Callable[[Tag], str | None]


@dataclass(frozen=True)
class ChoiceView:
    """A champion as the slot picker lists it: "Name, 6★ L60 #id" (the form reads the id)."""

    label: str


@dataclass(frozen=True)
class SlotView:
    """A team slot: its champion (None when open), as the picker shows it, and whether the
    search suggested it (else the user chose it) and the team needs it. `problem`: why the
    text typed in it isn't a champion (the slot stays open, the text kept)."""

    champion: ChampionRow | None
    choice: str  # the picker's text; "" when open
    suggested: bool
    needed: bool
    problem: str | None = None


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
    have; `faction`: only a champion of it gets the relic's skill."""

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
    return TeamView(
        slots=[slot_view(member, pick) for member, pick in zip(members, ask.picks, strict=True)],
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
    return GearView(gear.key, gear.name, gear.faction, on, sorted(brings, key=lambda i: i.label))


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
