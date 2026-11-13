"""mitmproxy addon: lets the web UI send builds to the game through the HellHades extractor.
The account itself comes from the memory reader (`reader/`, `just read`); the extractor's
uploads pass through untouched and aren't kept.

The extractor holds a SignalR connection (JSON protocol, WebSocket) to HH's `/reader` hub, and
HH's server pushes commands down it. The control server injects one into that socket as if the
server had sent it, then waits for the extractor's `HelperRequestResult` reply (kept from HH's
server, as it never asked) and returns it:

- `POST http://127.0.0.1:8081/equip` `{"hero_id", "artifact_ids"}`: `EquipArtifacts`, the
  pieces really move
- `POST http://127.0.0.1:8081/preview` `{"account_id", "hero_id", "artifact_ids"}`:
  `PreviewBuild`, the game's build preview; nothing changes
- `POST http://127.0.0.1:8081/sell` `{"artifact_ids"}`: `SellArtifacts`, which selects the
  pieces in the game's sell screen; the sale is confirmed (or not) in game
"""

import asyncio
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mitmproxy import ctx, http

HOST = "raidoptimiser.hellhades.com"
HUB_PATH = "/reader"
CONTROL_ADDRESS = ("127.0.0.1", int(os.environ.get("RAID_CONTROL_PORT", "8081")))
RECORD_SEPARATOR = "\x1e"  # ends every SignalR JSON message
INVOCATION = 1
MAX_EQUIP = 16  # the extractor's own limits per request
MAX_PREVIEW = 9
MAX_SELL = 16384
RESULT_TIMEOUT = 30.0


@dataclass
class PendingResult:
    """An injected command waiting for the extractor's HelperRequestResult."""

    request: str
    operation_id: str | None
    done: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None


class HubControl:
    """Injects commands into the extractor's hub socket; see the module docstring."""

    def __init__(self) -> None:
        self._hub: http.HTTPFlow | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiting: PendingResult | None = None
        self._lock = threading.Lock()  # one injected command at a time

    def running(self) -> None:
        self._loop = asyncio.get_running_loop()
        server = ThreadingHTTPServer(CONTROL_ADDRESS, control_handler(self))
        threading.Thread(target=server.serve_forever, name="hh-control", daemon=True).start()
        logging.info(f"[hub] control on http://{CONTROL_ADDRESS[0]}:{CONTROL_ADDRESS[1]}")

    def websocket_start(self, flow: http.HTTPFlow) -> None:
        if is_hub(flow):
            self._hub = flow
            logging.info("[hub] extractor connected to the reader hub")

    def websocket_end(self, flow: http.HTTPFlow) -> None:
        if flow is self._hub:
            self._hub = None
            logging.info("[hub] extractor's hub socket closed")

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        if flow is not self._hub or (waiting := self._waiting) is None:
            return

        message = flow.websocket.messages[-1]
        if not message.from_client or not message.is_text:
            return

        match helper_results(message.text):
            case [result] if answers(result, waiting):
                message.drop()  # HH's server never asked for it
                waiting.result = result
                waiting.done.set()

    def equip(self, body: dict) -> tuple[int, dict]:
        """Status code and JSON body for the control endpoint."""
        hero_id = int(body["hero_id"])
        artifact_ids = [int(artifact_id) for artifact_id in body["artifact_ids"]]

        if reason := check_pieces(hero_id, artifact_ids, MAX_EQUIP):
            return 400, {"error": reason}

        return self._invoke("EquipArtifacts", [hero_id, artifact_ids], None)

    def preview(self, body: dict) -> tuple[int, dict]:
        account_id = int(body["account_id"])
        hero_id = int(body["hero_id"])
        artifact_ids = [int(artifact_id) for artifact_id in body["artifact_ids"]]

        if reason := check_pieces(hero_id, artifact_ids, MAX_PREVIEW):
            return 400, {"error": reason}

        if account_id <= 0:
            return 400, {"error": "account_id must be positive"}

        operation_id = str(uuid.uuid4())
        request = {
            "operationId": operation_id,
            "accountId": account_id,
            "heroId": hero_id,
            "artifactIds": artifact_ids,
        }
        return self._invoke("PreviewBuild", [request], operation_id)

    def sell(self, body: dict) -> tuple[int, dict]:
        artifact_ids = [int(artifact_id) for artifact_id in body["artifact_ids"]]

        if reason := check_ids(artifact_ids, MAX_SELL):
            return 400, {"error": reason}

        return self._invoke("SellArtifacts", [artifact_ids], None)

    def _invoke(self, target: str, arguments: list, operation_id: str | None) -> tuple[int, dict]:
        if not self._lock.acquire(blocking=False):
            return 409, {"error": "another command is still running"}

        try:
            return self._send(target, arguments, operation_id)
        finally:
            self._waiting = None
            self._lock.release()

    def _send(self, target: str, arguments: list, operation_id: str | None) -> tuple[int, dict]:
        hub, loop = self._hub, self._loop
        if hub is None or loop is None:
            return 503, {"error": "the extractor isn't connected through the proxy"}

        self._waiting = waiting = PendingResult(target, operation_id)
        frame = json.dumps({"type": INVOCATION, "target": target, "arguments": arguments})
        loop.call_soon_threadsafe(inject, hub, frame + RECORD_SEPARATOR)
        logging.info(f"[hub] injected {target} {arguments}")

        if not waiting.done.wait(RESULT_TIMEOUT):
            return 504, {"error": f"no reply from the extractor in {RESULT_TIMEOUT:g}s"}

        if error := field_of(waiting.result, "error"):
            return 502, {"error": error}

        return 200, {"ok": True}


def is_hub(flow: http.HTTPFlow) -> bool:
    path = flow.request.path.split("?")[0].rstrip("/").lower()
    return flow.request.pretty_host == HOST and path == HUB_PATH


def check_pieces(hero_id: int, artifact_ids: list[int], most: int) -> str | None:
    if hero_id <= 0:
        return "hero_id must be positive"

    return check_ids(artifact_ids, most)


def check_ids(artifact_ids: list[int], most: int) -> str | None:
    if not 1 <= len(artifact_ids) <= most:
        return f"between 1 and {most} artifacts per request"

    if any(artifact_id <= 0 for artifact_id in artifact_ids):
        return "artifact ids must be positive"

    if len(set(artifact_ids)) != len(artifact_ids):
        return "artifact ids must be distinct"

    return None


def answers(result: dict, waiting: PendingResult) -> bool:
    """Whether a HelperRequestResult is the reply to the injected command."""
    if field_of(result, "request") != waiting.request:
        return False

    return waiting.operation_id is None or field_of(result, "operationId") == waiting.operation_id


def inject(hub: http.HTTPFlow, frame: str) -> None:
    ctx.master.commands.call("inject.websocket", hub, True, frame.encode(), True)


def helper_results(text: str) -> list[dict]:
    """The HelperRequestResult arguments among a frame's SignalR messages."""
    results = []

    for record in filter(None, text.split(RECORD_SEPARATOR)):
        try:
            message = json.loads(record)
        except ValueError:
            continue

        if message.get("type") == INVOCATION and message.get("target") == "HelperRequestResult":
            results.extend(arg for arg in message.get("arguments", []) if isinstance(arg, dict))

    return results


def field_of(result: dict | None, name: str):
    """A result field, whichever casing the extractor's JSON serialiser used."""
    if result is None:
        return None

    return result.get(name, result.get(name[0].upper() + name[1:]))


def control_handler(control: HubControl) -> type[BaseHTTPRequestHandler]:
    class ControlHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            commands = {
                "/equip": control.equip,
                "/preview": control.preview,
                "/sell": control.sell,
            }
            if (command := commands.get(self.path.rstrip("/"))) is None:
                return self._reply(404, {"error": "unknown path"})

            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                self._reply(*command(body))
            except (ValueError, KeyError, TypeError) as e:
                self._reply(400, {"error": f"bad request: {e}"})

        def _reply(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:
            logging.debug(f"[hub] control: {format % args}")

    return ControlHandler


addons = [HubControl()]
