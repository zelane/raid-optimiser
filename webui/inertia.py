"""
inertia.py - the server side of Inertia.js (v3's protocol): a page is a Vue component and its
props. A browser's first load gets the HTML shell with the page in it; the client's own visits
(`X-Inertia`) get the page as JSON, and a partial reload only the props it names.

- `Prop`, `Props`: a page's props: values, or zero-argument callables evaluated only when sent
- `Page`: the page object the client reads
- `Assets`: the built front end's tags and version (Vite's manifest), or the dev server's
- `respond`: a page as the response the request wants
- `redirect`, `back`: after a form's POST (303, so the client follows with a GET); `back` can
  carry the form's errors to the page it returns to (`ERRORS_COOKIE`: there are no sessions)
- `to_json`: a view as JSON, as props are sent
- `current_assets`, `selected_props`, `page_json`, `flashed_errors`: what `respond` uses
"""

import base64
import binascii
import hashlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import orjson
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "static" / "dist" / ".vite" / "manifest.json"
ENTRY = "src/app.ts"
DIST_URL = "/static/dist/"
SHELL = "inertia.html"
ERRORS_COOKIE = "inertia_errors"  # a form's errors, read (and cleared) by the next page

type Prop = object | Callable[[], object]
type Props = Mapping[str, Prop]


@dataclass(frozen=True)
class Page:
    component: str
    props: dict[str, object]
    url: str
    version: str


@dataclass(frozen=True)
class Assets:
    """`dev_server`: Vite's dev server (VITE_DEV), which serves the entry itself."""

    version: str
    scripts: tuple[str, ...]
    styles: tuple[str, ...]
    dev_server: str | None = None


def respond(request: Request, templates: Jinja2Templates, component: str, props: Props) -> Response:
    assets = current_assets()
    inertia = request.headers.get("X-Inertia") == "true"
    stale = request.headers.get("X-Inertia-Version", assets.version) != assets.version

    if inertia and stale and request.method == "GET":
        return Response(
            status_code=409,
            headers={"X-Inertia-Location": str(request.url), "X-Inertia-Version": assets.version},
        )

    props = {"errors": flashed_errors(request), **props}
    sent = selected_props(request, component, props) if inertia else props
    page = Page(component, evaluate(sent), url_of(request), assets.version)

    if inertia:
        headers = {"X-Inertia": "true", "Vary": "X-Inertia"}
        response = Response(page_json(page), media_type="application/json", headers=headers)
    else:
        context = {"page_json": page_json(page).decode(), "assets": assets}
        response = templates.TemplateResponse(request, SHELL, context)
        response.headers["Vary"] = "X-Inertia"

    if ERRORS_COOKIE in request.cookies:
        response.delete_cookie(ERRORS_COOKIE)

    return response


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def back(request: Request, errors: Mapping[str, str] | None = None) -> RedirectResponse:
    """Back to the page that sent the form, as it was (its query and all), with what was wrong
    with the form (field -> message) in its `errors` prop."""
    response = redirect(request.headers.get("Referer") or "/")

    if errors:
        encoded = base64.urlsafe_b64encode(orjson.dumps(errors)).decode()
        response.set_cookie(ERRORS_COOKIE, encoded, httponly=True, samesite="strict")

    return response


def flashed_errors(request: Request) -> dict[str, str]:
    """The errors `back` left for this page; a cookie that doesn't read is none."""
    if not (encoded := request.cookies.get(ERRORS_COOKIE)):
        return {}

    try:
        errors = orjson.loads(base64.urlsafe_b64decode(encoded))
    except (binascii.Error, orjson.JSONDecodeError):
        return {}

    if not isinstance(errors, dict):
        return {}

    return {str(field): str(message) for field, message in errors.items()}


def current_assets() -> Assets:
    if dev_server := os.environ.get("VITE_DEV"):
        server = dev_server.rstrip("/")
        scripts = (f"{server}{DIST_URL}@vite/client", f"{server}{DIST_URL}{ENTRY}")
        return Assets("dev", scripts, (), dev_server=server)

    if not MANIFEST.exists():
        raise RuntimeError("the front end isn't built: run `just frontend-build`")

    return assets_for(MANIFEST.stat().st_mtime_ns)


@lru_cache(maxsize=1)
def assets_for(manifest_mtime: int) -> Assets:  # the mtime is only the cache key
    raw = MANIFEST.read_bytes()
    entry = orjson.loads(raw)[ENTRY]
    return Assets(
        version=hashlib.sha1(raw).hexdigest()[:16],
        scripts=(DIST_URL + entry["file"],),
        styles=tuple(DIST_URL + css for css in entry.get("css", ())),
    )


def selected_props(request: Request, component: str, props: Props) -> Props:
    """A partial reload of this component gets only the props it asks for (`-Partial-Data`),
    less those it doesn't want (`-Partial-Except`); `errors` always goes."""
    if request.headers.get("X-Inertia-Partial-Component") != component:
        return props

    wanted = header_keys(request, "X-Inertia-Partial-Data") or set(props)
    unwanted = header_keys(request, "X-Inertia-Partial-Except")
    return {
        key: value
        for key, value in props.items()
        if key == "errors" or (key in wanted and key not in unwanted)
    }


def header_keys(request: Request, header: str) -> set[str]:
    return {key.strip() for key in request.headers.get(header, "").split(",") if key.strip()}


def evaluate(props: Props) -> dict[str, object]:
    return {key: value() if callable(value) else value for key, value in props.items()}


def url_of(request: Request) -> str:
    query = request.url.query
    return request.url.path + (f"?{query}" if query else "")


def page_json(page: Page) -> bytes:
    """The page as JSON, safe inside the shell's `<script>` (no `<` to close it)."""
    return to_json(page).replace(b"<", b"\\u003c")


def to_json(value: object) -> bytes:
    """A view as a component gets it: dataclasses as objects, tuples as arrays."""
    return orjson.dumps(value, default=plain)


def plain(value: object) -> object:
    """What orjson can't serialise itself."""
    match value:
        case frozenset() | set():
            return sorted(value)

        case Path():
            return str(value)

    raise TypeError(f"can't send a {type(value).__name__} as a prop")
