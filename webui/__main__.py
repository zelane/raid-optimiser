"""
__main__.py - `python -m webui`: the web UI on http://127.0.0.1:8000 (`--port N`), restarting
itself when the Python under `optimiser/` or `webui/` changes (`--no-reload` to turn that off).

- `ROOT`, `WATCHED`: what the reloader watches
- `main`: the entry point
"""

import argparse
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
WATCHED = [ROOT / "optimiser", ROOT / "webui"]


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m webui")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    reload = not args.no_reload
    uvicorn.run(
        "webui.app:app",
        host="127.0.0.1",
        port=args.port,
        reload=reload,
        reload_dirs=[str(path) for path in WATCHED] if reload else None,
    )


main()
