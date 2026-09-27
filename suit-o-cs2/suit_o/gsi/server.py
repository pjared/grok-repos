"""Local HTTP server for CS2 Game State Integration.

The request handler checks the auth token and queues the payload. Detection
and speech run on a worker, so a slow voice line cannot stall CS2's POST.
"""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Full, Queue

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 1_000_000
_GSI_PATHS = frozenset({"/", ""})


class GsiServer(ThreadingHTTPServer):
    """Loopback HTTP server. daemon_threads so a stuck client cannot hang exit."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        queue: Queue,
        on_toggle_mute: Callable[[], bool],
        status: Callable[[], dict],
        on_rejected: Callable[[str], None] | None = None,
    ) -> None:
        self.token = token
        self.payload_queue = queue
        self.on_toggle_mute = on_toggle_mute
        self.status = status
        self.on_rejected = on_rejected
        super().__init__((host, port), GsiHandler)


class GsiHandler(BaseHTTPRequestHandler):
    server: GsiServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/status":
            body = json.dumps(self.server.status()).encode("utf-8")
            self._reply(200, body)
            return
        self._reply(404, b'{"error":"not found"}')

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/mute":
            muted = self.server.on_toggle_mute()
            body = json.dumps({"muted": muted}).encode("utf-8")
            self._reply(200, body)
            return
        if path not in _GSI_PATHS:
            self._reply(404, b'{"error":"not found"}')
            return

        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            self._reject(400, b'{"error":"bad content length"}', "bad content length")
            return
        if length < 0 or length > MAX_BODY_BYTES:
            self._reject(413, b'{"error":"payload too large"}', "payload too large")
            return
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reject(400, b'{"error":"invalid json"}', "invalid json")
            return
        if not isinstance(data, dict):
            self._reject(400, b'{"error":"json object required"}', "json object required")
            return
        provided = ""
        auth = data.get("auth")
        if isinstance(auth, dict) and auth.get("token") is not None:
            provided = str(auth.get("token"))
        if not _tokens_match(self.server.token, provided):
            logger.warning("Rejected GSI payload from %s: auth token mismatch", self.client_address[0])
            self._reject(401, b'{"error":"unauthorized"}', "bad token")
            return
        try:
            self.server.payload_queue.put_nowait(data)
        except Full:
            logger.warning("GSI queue is full; dropping a payload so the HTTP handler can return")
            self._reject(200, b'{"ok":true}', "queue full")
            return
        self._reply(200, b'{"ok":true}')

    def _reject(self, code: int, body: bytes, reason: str) -> None:
        callback = self.server.on_rejected
        if callback is not None:
            try:
                callback(reason)
            except Exception:
                logger.exception("Could not record a rejected GSI payload")
        self._reply(code, body)

    def _reply(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        logger.debug("gsi http: " + fmt, *args)


def _tokens_match(expected: str, provided: str) -> bool:
    return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))
