"""
team_gear.py - the team gear page's query into a `GearAsk`. The page's state is all in its
URL (a GET form).

Fields: the team's slots (`slot`, `relic`: `forms.team`); then a row per slot, its fields
ending in the slot's number (1 first): `set_<slot>` (repeated, up to `SETS_PER_ROW`: a set id,
empty for none) each with `pieces_<slot>` (in the same order; empty: the set's smallest
bonus), `min_SPD_<slot>`, `min_ACC_<slot>`, `min_RES_<slot>`, `min_CR_<slot>` (C.RATE in %),
`rank_<slot>` (a `Stat` name or `DAMAGE`; empty: SPD) and `skill_<slot>` (the skill whose
damage it ranks; empty: the champion's default). A minimum left out of the query (not sent
empty) takes its default (`Default`): ACC near the resist floor against the target's RES
(`accuracy.accuracy_for_floor`) for a champion who places debuffs, C.RATE 100 % for one
ranking damage, none for SPD and RES; `res` is the RES the page's ACC defaults came from, so
ACC still at its default follows a new target. `target` is the target picker's pick
("<stage>:<wave>:<slot>"). `filters`: the gear filters are as sent (`unworn_only`, `locked`
with `lock_level`, `exclude_<rule key>`), else every reserve rule applies. `run` solves.

- `SIZE`, `SETS_PER_ROW`, `DAMAGE`, `ROW_MINIMUMS`, `Default`, `Minimum`: a row's shape
- `RowFields`, `row_fields`, `minimum_field`, `PageFields`, `PAGE_FIELDS`: the query's names,
  which the page is given (`service.team_gear`) so it never spells them itself
- `RowAsk`, `GearAsk`: what's asked
- `parse_gear_ask`: the boundary
- `parse_row`, `parse_set_picks`, `parse_minimum`, `parse_rank`, `filter_fields`, `last`: its
  steps
"""

from collections.abc import Mapping
from dataclasses import dataclass

from optimiser.account import Account, FixedSet, Stat
from optimiser.reserve import Rule
from optimiser.solve import MAX_PIECES, GearFilter
from webui.forms.common import FormErrors
from webui.forms.request import exclude_field, parse_gear_filter
from webui.forms.targets import SavedTarget, parse_saved
from webui.forms.team import TRUE, SlotPick, parse_slots

SIZE = 5
SETS_PER_ROW = 2
DAMAGE = "DAMAGE"
ROW_MINIMUMS = (Stat.SPD, Stat.ACC, Stat.RES, Stat.CR)


@dataclass(frozen=True)
class RowFields:
    """A slot's row's fields: `sets` and `pieces` repeated (in step), the rest once; each
    minimum's is `minimum_field`."""

    sets: str
    pieces: str
    rank: str
    skill: str


def row_fields(slot: int) -> RowFields:
    return RowFields(f"set_{slot}", f"pieces_{slot}", f"rank_{slot}", f"skill_{slot}")


def minimum_field(stat: Stat, slot: int) -> str:
    return f"min_{stat.name}_{slot}"


@dataclass(frozen=True)
class PageFields:
    """The page's own fields: the slots (`slot`, repeated), the target picked, the RES its ACC
    defaults came from, the marker that the gear filters are as sent, the filter for unworn
    gear only, and the one that solves."""

    slot: str
    target: str
    res: str
    filters: str
    unworn_only: str
    run: str


PAGE_FIELDS = PageFields("slot", "target", "res", "filters", "unworn_only", "run")


@dataclass(frozen=True)
class Default:
    """A minimum the page fills in: left out of the query."""


type Minimum = float | Default | None  # None: no minimum


@dataclass(frozen=True)
class RowAsk:
    """A slot's row as asked: sets (id -> pieces), minimums (C.RATE as a fraction), what it
    ranks (a stat, or `DAMAGE` with `skill`: None for the champion's default)."""

    sets: dict[int, int]
    minimums: dict[Stat, Minimum]
    rank: Stat | str
    skill: int | None


@dataclass(frozen=True)
class GearAsk:
    picks: tuple[SlotPick, ...]
    rows: tuple[RowAsk, ...]  # one per slot
    target: SavedTarget | None
    defaults_res: float | None  # the RES the ACC defaults came from
    gear: GearFilter
    filters_sent: bool
    run: bool


def parse_gear_ask(
    query: Mapping[str, list[str]], account: Account, rules: tuple[Rule, ...], locks
) -> GearAsk | FormErrors:
    errors: list[str] = []
    fields = PAGE_FIELDS
    picks = parse_slots(query.get(fields.slot, []), account, SIZE)
    rows = tuple(parse_row(query, slot, account, errors) for slot in range(1, SIZE + 1))
    filters_sent = fields.filters in query
    gear = parse_gear_filter(
        filter_fields(query, rules, filters_sent), account, locks, rules, errors
    )
    res_text = last(query, fields.res)

    if isinstance(picks, FormErrors):
        errors += picks.messages

    if errors or isinstance(picks, FormErrors):
        return FormErrors(errors)

    return GearAsk(
        picks=picks,
        rows=rows,
        target=parse_saved(last(query, fields.target)),
        defaults_res=float(res_text) if res_text.replace(".", "", 1).isdigit() else None,
        gear=gear,
        filters_sent=filters_sent,
        run=last(query, fields.run).lower() in TRUE,
    )


def last(query: Mapping[str, list[str]], name: str) -> str:
    return (query.get(name) or [""])[-1].strip()


def parse_row(
    query: Mapping[str, list[str]], slot: int, account: Account, errors: list[str]
) -> RowAsk:
    fields = row_fields(slot)
    rank = parse_rank(last(query, fields.rank), slot, errors)
    skill = last(query, fields.skill)
    return RowAsk(
        sets=parse_set_picks(
            query.get(fields.sets, []), query.get(fields.pieces, []), slot, account, errors
        ),
        minimums={
            stat: parse_minimum(query, minimum_field(stat, slot), stat, slot, errors)
            for stat in ROW_MINIMUMS
        },
        rank=rank,
        skill=int(skill) if skill.isdigit() else None,
    )


def parse_set_picks(
    set_texts: list[str], piece_texts: list[str], slot: int, account: Account, errors: list[str]
) -> dict[int, int]:
    """Each set picked, with its pieces (empty: the fewest that give it a bonus)."""
    sets = account.tables.sets
    picked: dict[int, int] = {}
    pieces = piece_texts + [""] * (len(set_texts) - len(piece_texts))

    for set_text, piece_text in zip(set_texts[:SETS_PER_ROW], pieces, strict=False):
        if not (set_text := set_text.strip()):
            continue

        if not set_text.isdigit() or int(set_text) not in sets:
            errors.append(f"slot {slot}: unknown set")
            continue

        artifact_set = sets[int(set_text)]
        match artifact_set:
            case FixedSet(pieces=size):
                fewest = size
            case _:
                fewest = min(artifact_set.totals, default=1)

        count = int(piece_text) if piece_text.strip().isdigit() else fewest
        if not 1 <= count <= MAX_PIECES:
            errors.append(f"slot {slot}: {artifact_set.name} pieces must be 1 to {MAX_PIECES}")
            continue

        picked[artifact_set.id] = picked.get(artifact_set.id, 0) + count

    return picked


def parse_minimum(
    query: Mapping[str, list[str]], field: str, stat: Stat, slot: int, errors: list[str]
) -> Minimum:
    if field not in query:
        return Default()

    if not (text := last(query, field)):
        return None

    try:
        value = float(text)
    except ValueError:
        errors.append(f"slot {slot}: {text!r} is not a number")
        return None

    return value / 100 if stat == Stat.CR else value


def parse_rank(text: str, slot: int, errors: list[str]) -> Stat | str:
    if not text:
        return Stat.SPD

    if text == DAMAGE:
        return DAMAGE

    if text in Stat.__members__:
        return Stat[text]

    errors.append(f"slot {slot}: can't rank {text!r}")
    return Stat.SPD


def filter_fields(
    query: Mapping[str, list[str]], rules: tuple[Rule, ...], sent: bool
) -> dict[str, str]:
    """The gear filters as `parse_gear_filter` reads them; not sent: every reserve rule."""
    if sent:
        return {name: values[-1] for name, values in query.items() if values}

    return {exclude_field(rule): "on" for rule in rules}
