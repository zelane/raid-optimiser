"""
test_inertia.py - the Inertia adapter (`webui.inertia`) over a page with a cheap and a lazy
prop, served from Vite's dev server (no build needed).

- `test_first_load_gets_the_shell_with_the_page`: HTML, the page object in its script element
- `test_a_visit_gets_the_page_as_json`: `X-Inertia`, with the default `errors`
- `test_partial_reload_sends_only_what_it_asks`: and never evaluates the rest
- `test_stale_assets_reload_the_page`: a version mismatch on GET is a 409 to the URL
- `test_redirect_after_a_post_is_a_see_other`: 303
- `test_errors_go_back_to_the_page_once`: a form's errors reach the next page, then are gone
"""

import json
import re

import pytest
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from webui import inertia

SHELL = '<script data-page="app" type="application/json">{{ page_json | safe }}</script>'
INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "dev"}


@pytest.fixture
def client(tmp_path, monkeypatch) -> tuple[TestClient, list[str]]:
    monkeypatch.setenv("VITE_DEV", "http://127.0.0.1:5173")
    tmp_path.joinpath(inertia.SHELL).write_text(SHELL)
    templates = Jinja2Templates(directory=tmp_path)
    evaluated: list[str] = []
    app = FastAPI()

    def slow() -> list[int]:
        evaluated.append("slow")
        return [1, 2]

    @app.get("/thing")
    def thing(request: Request):
        return inertia.respond(request, templates, "Thing", {"name": "</script>", "slow": slow})

    @app.post("/thing")
    def post_thing():
        return inertia.redirect("/thing")

    @app.post("/bad")
    def post_bad(request: Request):
        return inertia.back(request, {"form": "no such thing"})

    return TestClient(app), evaluated


def test_first_load_gets_the_shell_with_the_page(client) -> None:
    test_client, _ = client
    response = test_client.get("/thing?x=1")

    assert response.headers["content-type"].startswith("text/html")
    assert "</script>" not in response.text.removesuffix("</script>")
    found = re.search(r'type="application/json">(.*)</script>', response.text)
    page = json.loads(found.group(1)) if found else {}
    assert page["component"] == "Thing" and page["url"] == "/thing?x=1"
    assert page["props"]["name"] == "</script>"


def test_a_visit_gets_the_page_as_json(client) -> None:
    test_client, _ = client
    response = test_client.get("/thing", headers=INERTIA)

    assert response.headers["X-Inertia"] == "true"
    assert response.json()["props"] == {"errors": {}, "name": "</script>", "slow": [1, 2]}


def test_partial_reload_sends_only_what_it_asks(client) -> None:
    test_client, evaluated = client
    partial = {**INERTIA, "X-Inertia-Partial-Component": "Thing", "X-Inertia-Partial-Data": "name"}
    response = test_client.get("/thing", headers=partial)

    assert response.json()["props"] == {"errors": {}, "name": "</script>"}
    assert evaluated == []

    other = {**partial, "X-Inertia-Partial-Component": "Other"}
    assert "slow" in test_client.get("/thing", headers=other).json()["props"]


def test_stale_assets_reload_the_page(client) -> None:
    test_client, _ = client
    response = test_client.get("/thing", headers={**INERTIA, "X-Inertia-Version": "old"})

    assert response.status_code == 409
    assert response.headers["X-Inertia-Location"] == "http://testserver/thing"


def test_redirect_after_a_post_is_a_see_other(client) -> None:
    test_client, _ = client
    response = test_client.post("/thing", headers=INERTIA, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/thing"


def test_errors_go_back_to_the_page_once(client) -> None:
    test_client, _ = client
    sent_from = {**INERTIA, "Referer": "http://testserver/thing?x=1"}
    response = test_client.post("/bad", headers=sent_from)

    assert response.json()["url"] == "/thing?x=1"
    assert response.json()["props"]["errors"] == {"form": "no such thing"}
    assert test_client.get("/thing", headers=INERTIA).json()["props"]["errors"] == {}
