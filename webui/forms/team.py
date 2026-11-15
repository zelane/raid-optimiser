"""
team.py - a team finder's query, shared by the pages that find teams: `slot` (repeated, one
per team slot) is a champion picked from its list, which ends in "#<champion id>", or part of
a champion's name typed in, or empty for an open slot; `want` (repeated) a debuff, buff or
effect every team must bring (a `Tag.key`, one of `Offers.tags`); `gear` (repeated) a set or
relic any champion may wear (a `Gear.key`; `gear_set` present: the list is as sent, else the
defaults); `assume` (repeated) something assumed: "<tag key>" for the team, "<champion
id>@<tag key>" for one champion; `assume_what` and `assume_who`: the assume form's new entry;
`count` (repeated) so many different debuffs or buffs every team must bring ("debuff:3"),
`count_side` and `count_n`: the count form's new entry.
A search (`run`) lists `listed` teams, the page showing option number `option`.

- `GRADES`, `FIRST_SHOWN`, `MAX_LISTED`, `TRUE`: a search's shape
- `Offers`, `TeamAsk`, `Fill`: what it can pick from, and what it asks
- `parse_team`, `parse_fill`: the boundaries
- `Unmatched`, `SlotPick`, `parse_slots` (`parse_slot`): the team's slots
- `COUNT_SIDES`, `MOST_COUNTED`: what a count can ask for
- `parse_wanted`, `parse_counts`, `parse_gear`, `parse_assumed`, `assume_entry`, `count_entry`:
  its steps
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.teams.gear import DEFAULT_GEAR, Assumed, Gear, Loadout, assumed_gear
from optimiser.teams.needs import Distinct
from optimiser.teams.tags import Side, Tag
from webui.forms.common import FormErrors

GRADES = (6, 5, 4)
FIRST_SHOWN = 3  # teams a run lists at first
MAX_LISTED = 300  # most a page lists
TRUE = ("true", "1", "on", "yes")
COUNT_SIDES = (Side.DEBUFF, Side.BUFF)
MOST_COUNTED = 10


@dataclass(frozen=True)
class Unmatched:
    """Text typed in a slot that isn't one champion: kept for the user to fix, and why."""

    text: str
    reason: str


type SlotPick = Champion | Unmatched | None


@dataclass(frozen=True)
class Offers:
    """What a team finder can pick from: tags to want or assume, and gear to allow."""

    tags: list[Tag]
    gear: list[Gear]


@dataclass(frozen=True)
class Fill:
    """Search for teams around the slots: list the first `listed`, the trials showing option
    number `option` (the first, if there's no such option)."""

    listed: int
    option: int


@dataclass(frozen=True)
class TeamAsk:
    """The slots as typed, what every team must bring (tags, and so many different debuffs or
    buffs: `counts`), and what it can wear or is assumed to have."""

    picks: tuple[SlotPick, ...]
    wanted: tuple[Tag, ...]
    loadout: Loadout
    counts: tuple[Distinct, ...] = ()


def parse_team(
    query: Mapping[str, list[str]], account: Account, offers: Offers, size: int
) -> TeamAsk | FormErrors:
    """The team's fields (each name's values, in order), `size` slots."""
    picks = parse_slots(query.get("slot", []), account, size)
    wanted = parse_wanted(query.get("want", []), offers.tags)
    counts = parse_counts(query.get("count", []) + count_entry(query))
    allowed = query.get("gear", []) if "gear_set" in query else list(DEFAULT_GEAR)
    gear = parse_gear(allowed, offers.gear)
    entries = query.get("assume", []) + assume_entry(query, account)
    assumed = parse_assumed(entries, account, offers.tags)
    if (
        isinstance(picks, FormErrors)
        or isinstance(wanted, FormErrors)
        or isinstance(counts, FormErrors)
        or isinstance(gear, FormErrors)
        or isinstance(assumed, FormErrors)
    ):
        parsed = (picks, wanted, counts, gear, assumed)
        return FormErrors([m for p in parsed if isinstance(p, FormErrors) for m in p.messages])

    team_assumed, single = assumed
    return TeamAsk(picks, wanted, Loadout(gear + team_assumed, single), counts)


def assume_entry(query: Mapping[str, list[str]], account: Account) -> list[str]:
    """The assume form's new entry, if any: what (a tag key) and who (a champion as picked or
    typed; none: the team), as `parse_assumed` reads it."""
    what = (query.get("assume_what") or [""])[-1]
    if not what:
        return []

    who = parse_slot((query.get("assume_who") or [""])[-1].strip(), account)
    return [f"{who.id}@{what}" if isinstance(who, Champion) else what]


def count_entry(query: Mapping[str, list[str]]) -> list[str]:
    """The count form's new entry, if any, as `parse_counts` reads it."""
    side = (query.get("count_side") or [""])[-1]
    number = (query.get("count_n") or [""])[-1].strip()
    return [f"{side}:{number}"] if side and number else []


def parse_counts(texts: list[str]) -> tuple[Distinct, ...] | FormErrors:
    """Each "<side>:<n>" (debuffs or buffs, 1 to `MOST_COUNTED`) as so many different ones,
    once each, in order; a side counted twice keeps its last."""
    by_side: dict[Side, Distinct] = {}
    errors = []

    for text in texts:
        side, _, number = text.partition(":")
        if side not in COUNT_SIDES or not number.isdigit() or not 1 <= int(number) <= MOST_COUNTED:
            errors.append(f"can't count {text!r}")
        else:
            by_side.pop(Side(side), None)
            by_side[Side(side)] = Distinct(Side(side), int(number))

    return FormErrors(errors) if errors else tuple(by_side.values())


CHAMPION_ID = re.compile(r"#(\d+)\s*$")
SHOWN_MATCHES = 3


def parse_slots(texts: list[str], account: Account, size: int) -> tuple[SlotPick, ...] | FormErrors:
    """`size` slots, None where open; extra fields are an error, missing ones are open."""
    if len(texts) > size:
        return FormErrors([f"a team has {size} slots"])

    padded = texts + [""] * (size - len(texts))
    return tuple(parse_slot(text.strip(), account) for text in padded)


def parse_slot(text: str, account: Account) -> SlotPick:
    """A pick from the list ("… #<id>"), or a name typed in part: the best copy of the one
    champion whose name has it (an exact name wins)."""
    if not text:
        return None

    if match := CHAMPION_ID.search(text):
        champion = account.champions.get(int(match.group(1)))
        return champion or Unmatched(text, "no such champion")

    wanted = text.casefold()
    names = {c.name for c in account.champions.values() if wanted in c.name.casefold()}
    exact = {name for name in names if name.casefold() == wanted}

    match sorted(exact or names):
        case []:
            return Unmatched(text, "no champion matches")

        case [name]:
            copies = [c for c in account.champions.values() if c.name == name]
            return max(copies, key=lambda c: (c.grade, c.awakening, c.level))

        case several:
            shown = ", ".join(several[:SHOWN_MATCHES])
            more = "…" if len(several) > SHOWN_MATCHES else ""
            return Unmatched(text, f"matches {len(several)}: {shown}{more}")


def parse_wanted(keys: list[str], offered: list[Tag]) -> tuple[Tag, ...] | FormErrors:
    """The tags named (by `Tag.key`), in `offered`'s order, once each."""
    unknown = sorted(set(keys) - {tag.key for tag in offered})
    if unknown:
        return FormErrors([f"can't ask for {', '.join(unknown)}"])

    return tuple(tag for tag in offered if tag.key in keys)


def parse_gear(keys: list[str], offered: list[Gear]) -> tuple[Gear, ...] | FormErrors:
    """The gear named (by `Gear.key`, empty ones ignored), in `offered`'s order."""
    named = {key for key in keys if key}
    unknown = sorted(named - {gear.key for gear in offered})
    if unknown:
        return FormErrors([f"no such gear: {', '.join(unknown)}"])

    return tuple(gear for gear in offered if gear.key in named)


def parse_assumed(
    texts: list[str], account: Account, tags: list[Tag]
) -> tuple[tuple[Gear, ...], tuple[Assumed, ...]] | FormErrors:
    """What's assumed: for the team (as gear any champion wears) and for single champions."""
    by_key = {tag.key: tag for tag in tags}
    team: list[Gear] = []
    single: list[Assumed] = []
    errors = []

    for text in dict.fromkeys(t.strip() for t in texts if t.strip()):
        who, _, key = text.rpartition("@")
        tag = by_key.get(key)
        champion = account.champions.get(int(who)) if who.isdigit() else None
        if tag is None or (who and champion is None):
            errors.append(f"can't assume {text!r}")
        elif champion is None:
            team.append(assumed_gear(tag))
        else:
            single.append(Assumed(tag, champion))

    return FormErrors(errors) if errors else (tuple(team), tuple(single))


def parse_fill(query: Mapping[str, list[str]]) -> Fill:
    """How many teams to list (`FIRST_SHOWN` to `MAX_LISTED`) and which to show; numbers that
    aren't fall back to the first."""

    def number(name: str, default: int) -> int:
        text = (query.get(name) or [""])[-1]
        return int(text) if text.isdigit() else default

    listed = min(max(number("listed", FIRST_SHOWN), FIRST_SHOWN), MAX_LISTED)
    return Fill(listed, number("option", 1))
