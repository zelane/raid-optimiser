"""mitmproxy addon: tee HellHades extractor account uploads to disk and decode them, and let
the web UI equip builds in game through the extractor.

Capture: every `POST /api/Account/v2` the extractor sends to raidoptimiser.hellhades.com is
saved as data/captures/raw/<timestamp>.bin (raw MessagePack+LZ4, newest KEEP_RAW kept) and
decoded by the C# `raid-decoder` tool into data/captures/latest/*.json, which is replaced
atomically on each sync. The request itself is forwarded untouched.

The extractor re-uploads every ~15s while the game runs, so decodes are coalesced:
a single worker always decodes the newest pending capture and skips older ones.

Equip and preview: the extractor holds a SignalR connection (JSON protocol, WebSocket) to
HH's `/reader` hub, and HH's server pushes commands down it. The control server injects one
into that socket as if the server had sent it, then waits for the extractor's
`HelperRequestResult` reply (kept from HH's server, as it never asked) and returns it:

- `POST http://127.0.0.1:8081/equip` `{"hero_id", "artifact_ids"}`: `EquipArtifacts`, the
  pieces really move
- `POST http://127.0.0.1:8081/preview` `{"account_id", "hero_id", "artifact_ids"}`:
  `PreviewBuild`, the game's build preview; nothing changes, so no account sync follows
- `POST http://127.0.0.1:8081/sell` `{"artifact_ids"}`: `SellArtifacts`, which selects the
  pieces in the game's sell screen; the sale is confirmed (or not) in game
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mitmproxy import ctx, http

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = Path(os.environ.get("RAID_CAPTURES", ROOT / "data" / "captures"))
DECODER = ROOT / "bin" / "raid-decoder"
HOST = "raidoptimiser.hellhades.com"
KEEP_RAW = 20

HUB_PATH = "/reader"
CONTROL_ADDRESS = ("127.0.0.1", int(os.environ.get("RAID_CONTROL_PORT", "8081")))
RECORD_SEPARATOR = "\x1e"  # ends every SignalR JSON message
INVOCATION = 1
MAX_EQUIP = 16  # the extractor's own limits per request
MAX_PREVIEW = 9
MAX_SELL = 16384
RESULT_TIMEOUT = 30.0


class HHCapture:
    def __init__(self) -> None:
        self._pending: Path | None = None
        self._cond = threading.Condition()
        threading.Thread(target=self._worker, name="hh-decode", daemon=True).start()

    def request(self, flow: http.HTTPFlow) -> None:
        req = flow.request
        if req.method != "POST" or req.pretty_host != HOST:
            return
        if req.path.split("?")[0].rstrip("/").lower() != "/api/account/v2":
            return

        raw_dir = CAPTURES / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        body = req.raw_content or b""
        raw = raw_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}.bin"
        raw.write_bytes(body)
        for old in sorted(raw_dir.glob("*.bin"))[:-KEEP_RAW]:
            old.unlink(missing_ok=True)
        logging.info(f"[hh] captured account upload: {raw.name} ({len(body)} bytes)")

        with self._cond:
            self._pending = raw
            self._cond.notify()

    def _worker(self) -> None:
        while True:
            with self._cond:
                while self._pending is None:
                    self._cond.wait()
                raw, self._pending = self._pending, None
            try:
                self._decode(raw)
            except Exception as e:  # never let the worker die
                logging.error(f"[hh] decode crashed: {e}")

    def _decode(self, raw: Path) -> None:
        if not DECODER.exists():
            logging.warning(f"[hh] decoder not built ({DECODER}); keeping raw capture only")
            return
        tmp, latest, old = CAPTURES / ".latest.tmp", CAPTURES / "latest", CAPTURES / ".latest.old"
        shutil.rmtree(tmp, ignore_errors=True)
        res = subprocess.run([str(DECODER), str(raw), str(tmp)], capture_output=True, text=True)
        out = (res.stdout + res.stderr).strip()
        if res.returncode != 0:
            logging.error(f"[hh] decode failed for {raw.name}:\n{out}")
            shutil.rmtree(tmp, ignore_errors=True)
            return
        # Swap in the new export; `latest` is a symlink in older layouts.
        shutil.rmtree(old, ignore_errors=True)
        if latest.is_symlink():
            latest.unlink()
        elif latest.exists():
            latest.rename(old)
        tmp.rename(latest)
        shutil.rmtree(old, ignore_errors=True)
        logging.info(f"[hh] {out.splitlines()[-1] if out else 'decoded'}")


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


addons = [HHCapture(), HubControl()]
