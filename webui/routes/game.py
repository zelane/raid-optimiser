"""
game.py - the memory reader: a sync now, and `just watch` started or stopped.

- `router`: its routes, `sync`, `start_watch`, `stop_watch`
"""

from fastapi import APIRouter

from webui import reader
from webui.responses import (
    sent,
)

router = APIRouter()


@router.post("/sync")
def sync():
    """Reads the account; on success the layout reloads its page's props with it."""
    return sent(reader.sync())


@router.post("/watch/start")
def start_watch():
    """Starts `just watch`, which keeps the account current while the game runs."""
    return sent(reader.start_watch())


@router.post("/watch/stop")
def stop_watch():
    return sent(reader.stop_watch())
