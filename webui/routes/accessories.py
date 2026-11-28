"""
accessories.py - the Accessories page and its settings, saved in place (types, set fits, rules),
the clean-up's target and protections, and selling in the game.

- `router`: its routes, `accessories`, `accessory_type`, `add_accessory_type`,
  `copy_accessory_type`, `delete_accessory_type`, `accessory_set_value`, `accessory_set_target`,
  `accessory_set_rule`, `accessory_rule`, `accessory_off_target`, `accessory_target`,
  `protect_accessory`, `sell_accessories`
"""

from fastapi import APIRouter, HTTPException, Request

from webui import extractor, inertia
from webui.forms.common import FormErrors
from webui.forms.settings import (
    TypeEdit,
    parse_champion_type,
    parse_off_target,
    parse_protect,
    parse_rule_value,
    parse_sell,
    parse_set_rule,
    parse_set_target,
    parse_set_value,
    parse_target_free,
)
from webui.responses import (
    back_with,
    inertia_page,
    read_form,
    saved,
    sent,
)
from webui.result import Err
from webui.service import accessories as accessory_pages
from webui.service import current

router = APIRouter()


@router.get("/accessories")
def accessories(request: Request, tab: str = accessory_pages.ACCESSORY_TABS[0]):
    if tab not in accessory_pages.ACCESSORY_TABS:
        raise HTTPException(404, f"no tab {tab}")

    page = accessory_pages.accessories_page(current.current_account(), tab)
    return inertia_page(request, "Accessories", {"page": page})


WEIGHTS_TAB = "/accessories?tab=weights"


@router.post("/accessories/types")
async def accessory_type(request: Request):
    """A type's row, saved whole on each change; the lists re-plan with it on the next visit
    (rescoring is slow, so the page doesn't reload)."""
    account, form = current.current_account(), await read_form(request)

    match parse_champion_type(form, accessory_pages.type_factions(account)):
        case FormErrors() as errors:
            return saved(errors)

        case TypeEdit() as edit if accessory_pages.save_type(account, edit):
            return saved(None)

        case TypeEdit():
            return saved(FormErrors(["that type is gone; reload the page"]))


@router.post("/accessories/types/add")
def add_accessory_type():
    accessory_pages.add_type()
    return inertia.redirect(WEIGHTS_TAB)


@router.post("/accessories/types/{key}/copy")
def copy_accessory_type(key: str):
    accessory_pages.copy_type(current.current_account(), key)
    return inertia.redirect(WEIGHTS_TAB)


@router.post("/accessories/types/{key}/delete")
def delete_accessory_type(key: str):
    accessory_pages.delete_type(key)
    return inertia.redirect(WEIGHTS_TAB)


@router.post("/accessories/sets/value")
async def accessory_set_value(request: Request):
    match parse_set_value(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case value:
            accessory_pages.save_set_value(current.current_account(), value.set_id, value.factor)
            return saved(None)


@router.post("/accessories/sets/target")
async def accessory_set_target(request: Request):
    account, form = current.current_account(), await read_form(request)
    type_keys = {t.key for t in accessory_pages.current_types(account)}

    match parse_set_target(form, type_keys):
        case FormErrors() as errors:
            return saved(errors)

        case target:
            accessory_pages.save_set_target(account, target.set_id, target.type_key, target.on)
            return saved(None)


@router.post("/accessories/sets/rule")
async def accessory_set_rule(request: Request):
    match parse_set_rule(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case rule:
            accessory_pages.save_set_rule(
                current.current_account(), rule.set_id, rule.name, rule.value
            )
            return saved(None)


@router.post("/accessories/rule")
async def accessory_rule(request: Request):
    match parse_rule_value(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case rule:
            accessory_pages.save_rule(rule.name, rule.value)
            return saved(None)


@router.post("/accessories/off-target")
async def accessory_off_target(request: Request):
    match parse_off_target(await read_form(request)):
        case FormErrors() as errors:
            return saved(errors)

        case share:
            accessory_pages.save_off_target(share)
            return saved(None)


@router.post("/accessories/target")
async def accessory_target(request: Request):
    """The clean-up's spaces to leave free; back to the page, re-planned."""
    match parse_target_free(await read_form(request)):
        case FormErrors() as errors:
            return back_with(request, errors)

        case target:
            accessory_pages.set_target_free(target)
            return inertia.back(request)


@router.post("/accessories/{artifact_id}/protect")
async def protect_accessory(request: Request, artifact_id: int):
    form = await read_form(request)
    accessory_pages.protect_accessory(artifact_id, parse_protect(form))
    return inertia.back(request)


@router.post("/accessories/sell")
async def sell_accessories(request: Request):
    """Selects the pieces in the game's sell screen; the user confirms the sale there."""
    fields = [str(value) for value in (await request.form()).getlist("artifact_id")]

    match parse_sell(fields, accessory_pages.pieces_to_sell(current.current_account())):
        case FormErrors(messages=messages):
            outcome = Err("; ".join(messages))

        case artifact_ids:
            outcome = extractor.select_to_sell(artifact_ids)

    return sent(outcome)
