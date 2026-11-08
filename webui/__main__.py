"""
__main__.py - `python -m webui`: the web UI on http://127.0.0.1:8000, restarting itself when
the Python under `optimiser/` or `webui/` changes (`--no-reload` to turn that off).

- `ROOT`, `WATCHED`: what the reloader watches
- `main`: the entry point
"""

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
WATCHED = [ROOT / "optimiser", ROOT / "webui"]


def main() -> None:
    reload = "--no-reload" not in sys.argv[1:]
    uvicorn.run(
        "webui.app:app",
        host="127.0.0.1",
        port=8000,
        reload=reload,
        reload_dirs=[str(path) for path in WATCHED] if reload else None,
    )


main()
