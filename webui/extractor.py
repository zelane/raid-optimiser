"""
extractor.py - changes to the game, made by the HH extractor at our request. The capture
proxy (`capture/hh_capture.py`) injects the command into the extractor's hub connection and
answers once the extractor reports back.

- `CONTROL_URL`, `TIMEOUT`: where the proxy listens, and how long an equip may take
- `equip`: put pieces on a champion in game
- `preview`: show a champion in pieces in the game's build preview, changing nothing
- `select_to_sell`: select pieces in the game's sell screen; selling is confirmed in game
"""

import json
import os
import urllib.error
import urllib.request

from optimiser.account import Account
from webui.result import Err, Result

CONTROL_URL = os.environ.get("RAID_CONTROL_URL", "http://127.0.0.1:8081")
TIMEOUT = 40.0  # the proxy gives the extractor 30 s


def equip(champion_id: int, artifact_ids: list[int]) -> Result[None]:
    """Equip the pieces on the champion; pieces another champion wears move over."""
    return post("/equip", {"hero_id": champion_id, "artifact_ids": artifact_ids})


def preview(account: Account, champion_id: int, artifact_ids: list[int]) -> Result[None]:
    body = {"account_id": account.user_id, "hero_id": champion_id, "artifact_ids": artifact_ids}
    return post("/preview", body)


def select_to_sell(artifact_ids: list[int]) -> Result[None]:
    return post("/sell", {"artifact_ids": artifact_ids})


def post(path: str, body: dict) -> Result[None]:
    request = urllib.request.Request(
        CONTROL_URL + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT):
            return None

    except urllib.error.HTTPError as error:
        return Err(reason_from(error))

    except (urllib.error.URLError, TimeoutError) as error:
        return Err(f"the capture proxy isn't reachable ({error}); is `just proxy` running?")


def reason_from(error: urllib.error.HTTPError) -> str:
    try:
        return json.loads(error.read())["error"]
    except (ValueError, KeyError, TypeError):
        return f"the proxy answered {error.code}"
