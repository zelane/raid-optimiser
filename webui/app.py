"""
app.py - the web entry point: the FastAPI app, its static files and its routes (`webui.routes`,
a router per area), which hand the service's views to Vue pages (Inertia, `webui/inertia.py`),
take forms and answer components' own requests as JSON (`webui.responses`). Only the app, its
routes and responses, `inertia.py` and the page shell (`templates/inertia.html`) know about
HTTP or HTML.

- `app`: the FastAPI app
- `CachedStatic`: the static files, cached by the browser (versioned URLs for good)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from webui.routes import accessories, champions, config, game, info, sims, teams

HERE = Path(__file__).resolve().parent


class CachedStatic(StaticFiles):
    """Static files with a `Cache-Control`: without one the browser revalidates every image on
    each page (the art's files are new after each extract, so heuristic freshness is short),
    and the tiles' frames and portraits pop in. A `static_url` (`?v=`) never changes; the art
    changes only when re-extracted, so a day's staleness is fine (a hard reload clears it)."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)

        if response.status_code == 200:
            versioned = b"v=" in scope.get("query_string", b"")
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable" if versioned else "public, max-age=86400"
            )

        return response


app = FastAPI(title="Raid optimiser")
app.mount("/static", CachedStatic(directory=HERE / "static"), name="static")

app.include_router(champions.router)
app.include_router(config.router)
app.include_router(accessories.router)
app.include_router(teams.router)
app.include_router(sims.router)
app.include_router(info.router)
app.include_router(game.router)
