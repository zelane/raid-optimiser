"""
info.py - the Info pages (stages, events and their shard plans, masteries, skill books, empower)
and the palette.

- `router`: its routes, `palette`, `info`, `events`, `event_shards`, `masteries`, `books`,
  `empower`
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from optimiser.paths import EVENTS
from webui import reader
from webui.forms.books import parse_books_query
from webui.forms.finder import FinderQuery
from webui.responses import (
    inertia_page,
    view_json,
)
from webui.service import books as book_pages
from webui.service import current
from webui.service import empower as empower_pages
from webui.service import events as event_pages
from webui.service import finder as finder_pages
from webui.service import info as info_pages
from webui.service import masteries as mastery_pages
from webui.service import summons as summon_pages

router = APIRouter()


@router.get("/palette")
def palette(request: Request):
    """The theme's colours and the shared components, for checking the palette in place: a
    champion of each rarity the account has."""
    view = finder_pages.find_champions(
        current.current_account(), current.current_locks(), FinderQuery()
    )
    by_rarity = {}

    for row in view.picks:
        by_rarity.setdefault(row.champion.rarity, row.champion)

    return inertia_page(request, "Palette", {"champions": list(by_rarity.values())})


@router.get("/empower")
def empower(request: Request, rarity: str = empower_pages.DEFAULT_RARITY):
    account = current.current_account()
    if rarity not in empower_pages.empowerable_rarities(account):
        raise HTTPException(404, f"{rarity} champions can't be empowered")

    page = empower_pages.empower_page(account, rarity)
    return inertia_page(request, "Empower", {"page": page})


@router.get("/info")
def info(request: Request):
    page = info_pages.info_page(current.current_account(), current.current_enemies())
    return inertia_page(request, "Info", {"page": page})


@router.get("/events")
def events(request: Request):
    """The events on, as the reader last read them (the page polls this, for `just watch`):
    none if it found none."""
    if (found := current.current_events()) is None:
        return inertia_page(request, "Events", {"page": None})

    _, relics = current.current_effect_sources()
    names = {relic.id: relic.name for relic in relics}
    page = event_pages.events_page(
        current.current_account(),
        found,
        names,
        current.current_plan_tables(),
        datetime.now(UTC),
        reader.age_text(EVENTS),
    )
    return inertia_page(request, "Events", {"page": page})


@router.get("/events/{event_id}/shards")
def event_shards(event_id: int, short: int):
    """The shards each type takes to earn `short` more points in the event (the shard plan
    asks as its target or the champions counted by hand change), as JSON."""
    found = current.current_events()
    summoning = current.current_summoning()
    event = next((e for e in found.events if e.id == event_id), None) if found else None

    if event is None or summoning is None:
        raise HTTPException(404, f"no event {event_id} with summons")

    return view_json(summon_pages.shard_rows(event, summoning, short, datetime.now(UTC)))


@router.get("/masteries")
def masteries(request: Request):
    page = mastery_pages.masteries_page(current.current_account())
    return inertia_page(request, "Masteries", {"page": page})


@router.get("/books")
def books(request: Request):
    """The champions short of skill books, as the champion filter bar narrows them:
    rarity and stars start at their `forms.books` defaults, the rest of the bar at any."""
    query = parse_books_query(request.query_params)
    page = book_pages.books_page(current.current_account(), query)
    return inertia_page(request, "Books", {"page": page})
