"""
config.py - the Config page: what solves assume, glyphs to plan, and the reserve rules.

- `router`: its routes, `config`, `old_config`, `set_assumption`, `plan_glyph`, `reserve_rule`
"""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from webui import inertia
from webui.forms.common import FormErrors
from webui.forms.settings import (
    FlagSetting,
    GlyphPlan,
    ReserveSetting,
    parse_flag,
    parse_glyph,
    parse_reserve_rule,
)
from webui.responses import (
    back_with,
    inertia_page,
    read_form,
)
from webui.service import assumptions as assumption_pages
from webui.service import current

router = APIRouter()


@router.get("/config")
def config(request: Request):
    """What solves assume and what gear they keep out (the store's settings)."""
    page = assumption_pages.assumptions_page(current.current_account())
    return inertia_page(request, "Config", {"page": page})


@router.get("/assumptions")
def old_config():
    """The page's old address."""
    return RedirectResponse("/config", status_code=301)


@router.post("/assumptions")
async def set_assumption(request: Request):
    form = await read_form(request)

    match parse_flag(form):
        case FormErrors() as errors:
            return back_with(request, errors)

        case FlagSetting(flag=flag, on=on):
            assumption_pages.set_assumption(flag, on)
            return inertia.back(request)


@router.post("/glyphs")
async def plan_glyph(request: Request):
    account = current.current_account()
    form = await read_form(request)

    match parse_glyph(form, account.tables):
        case FormErrors() as errors:
            return back_with(request, errors)

        case GlyphPlan(kind=kind, grade=grade):
            assumption_pages.plan_glyph_for(kind, grade)
            return inertia.back(request)


@router.post("/reserve")
async def reserve_rule(request: Request):
    account = current.current_account()
    form = await read_form(request)

    match parse_reserve_rule(form, account):
        case FormErrors() as errors:
            return back_with(request, errors)

        case ReserveSetting(rule=rule, on=on):
            assumption_pages.change_reserve_rule(rule, on)
            return inertia.back(request)
