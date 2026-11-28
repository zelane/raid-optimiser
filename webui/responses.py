"""
responses.py - what the routes (`webui.routes`) answer with, and what they share: a Vue page
with the props every page gets (`inertia_page`), back to a form with its errors (`back_with`), a
component's own request answered as JSON (`sent`, `saved`, `view_json`), the posted form and the
champion it's for, and the shell's templates (`templates`, `static_url`).

- `templates`, `static_url`: the page shell, and a static file's URL that changes with the file
- `inertia_page`, `optimiser_url`: a Vue page, and the nav's Optimiser link
- `back_with`, `sent`, `saved`, `view_json`: other answers
- `read_form`, `finder_query`, `find_champion`: what a request carries
"""

from pathlib import Path

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from optimiser.account import Account, Champion
from webui import inertia, reader
from webui.forms.common import FormErrors
from webui.forms.finder import FinderQuery, parse_finder_query
from webui.result import Result, failed
from webui.service import layout, runs

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["static_url"] = lambda path: static_url(path)


def sent(outcome: Result[None]) -> JSONResponse:
    """A command to the game, done or why not."""
    return JSONResponse({"error": outcome.reason if failed(outcome) else None})


def saved(errors: FormErrors | None) -> JSONResponse:
    """A setting saved in place (no reload): what was wrong, or null."""
    return JSONResponse({"error": "; ".join(errors.messages) if errors else None})


def view_json(view: object) -> Response:
    return Response(inertia.to_json(view), media_type="application/json")


def finder_query(request: Request) -> FinderQuery:
    lists = {name: request.query_params.getlist(name) for name in request.query_params}
    return parse_finder_query(request.query_params, lists)


def back_with(request: Request, errors: FormErrors) -> Response:
    """Back to the form's page, its errors shown there (the layout's alert)."""
    return inertia.back(request, {"form": "; ".join(errors.messages)})


def inertia_page(request: Request, component: str, props: inertia.Props) -> Response:
    """A Vue page, with what every page gets: the frame's nav and sync age."""

    def frame() -> layout.Layout:
        return layout.layout_view(
            request.url.path, optimiser_url(), reader.synced_ago(), reader.watching()
        )

    return inertia.respond(request, templates, component, {"layout": frame, **props})


async def read_form(request: Request) -> dict[str, str]:
    """The posted form's fields, each name's last value."""
    return {key: str(value) for key, value in (await request.form()).items()}


def find_champion(account: Account, champion_id: int) -> Champion:
    if (champion := account.champions.get(champion_id)) is None:
        raise HTTPException(404, f"no champion {champion_id}")

    return champion


def optimiser_url() -> str:
    if (champion_id := runs.last_solved()) is not None:
        return f"/champions/{champion_id}"

    return "/"


def static_url(path: str) -> str:
    modified = HERE.joinpath("static", path).stat().st_mtime_ns
    return f"/static/{path}?v={modified}"
