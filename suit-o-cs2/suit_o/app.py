"""Wire the GSI server, event detector, line provider, and speech queue."""

from __future__ import annotations

import logging
import sys
import threading
import time
from queue import Empty, Full, Queue

from suit_o.config import Config
from suit_o.events.detector import EventDetector
from suit_o.gsi.parse import parse_payload
from suit_o.gsi.server import GsiServer
from suit_o.lines.provider import LineProvider, YamlLineProvider
from suit_o.models import GameEvent, Utterance
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.factory import create_backend
from suit_o.speech.service import SpeechService

logger = logging.getLogger(__name__)


class SuitOApp:
    def __init__(
        self,
        config: Config,
        *,
        backend: SpeechBackend | None = None,
        line_provider: LineProvider | None = None,
        clock=None,
    ) -> None:
        self.config = config
        self._clock = clock or time.monotonic
        self.backend = backend if backend is not None else create_backend(config.speech)
        self.speech = SpeechService(self.backend, config.preempt_min_priority)
        self.lines = line_provider or YamlLineProvider.from_file(
            config.lines_path,
            cooldowns=config.cooldowns,
            default_cooldown=config.default_cooldown,
            min_interval=config.min_interval,
            preempt_min_priority=config.preempt_min_priority,
            muted=config.mute,
        )
        if hasattr(self.lines, "set_muted"):
            self.lines.set_muted(config.mute)
        self.detector = EventDetector(config.thresholds)
        self._queue: Queue = Queue(maxsize=128)
        self.processed = 0
        self._httpd: GsiServer | None = None
        self._http_thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._did_stop = False
        self._started = False

    def start(self, *, console: bool = False) -> None:
        if self._started:
            return
        self._started = True
        self.speech.start()
        self.speech.set_muted(bool(getattr(self.lines, "muted", self.config.mute)))
        self._worker = threading.Thread(target=self._worker_loop, name="suit-o-gsi", daemon=True)
        self._worker.start()
        self._httpd = GsiServer(
            self.config.server.host,
            self.config.server.port,
            self.config.server.token,
            self._queue,
            self.toggle_mute,
            self.status,
        )
        self._http_thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="suit-o-http",
            daemon=True,
        )
        self._http_thread.start()
        if console and sys.stdin is not None and sys.stdin.isatty():
            threading.Thread(target=self._stdin_loop, name="suit-o-console", daemon=True).start()

    @property
    def server_address(self) -> tuple[str, int]:
        if self._httpd is None:
            raise RuntimeError("Suit-O is not listening yet")
        host, port = self._httpd.server_address[:2]
        return str(host), int(port)

    def wait_for_payloads(self, count: int, timeout: float = 5.0) -> bool:
        return self.speech.wait_until(lambda: self.processed >= count, timeout)

    def wait_forever(self) -> None:
        while not self._did_stop:
            time.sleep(0.2)

    def toggle_mute(self) -> bool:
        muted = not bool(getattr(self.lines, "muted", False))
        if hasattr(self.lines, "set_muted"):
            self.lines.set_muted(muted)
        else:
            self.lines.muted = muted
        self.speech.set_muted(muted)
        logger.info("Suit-O is %s", "muted" if muted else "listening")
        return muted

    def status(self) -> dict:
        return {
            "muted": bool(getattr(self.lines, "muted", False)),
            "received": self.processed,
            "spoken": len(self.speech.history),
        }

    def stop(self) -> None:
        if self._did_stop:
            return
        self._did_stop = True
        self._stop.set()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        if self._worker is not None:
            self._worker.join(timeout=2)
        self.speech.stop()
        if self._http_thread is not None:
            self._http_thread.join(timeout=2)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if item is None:
                break
            try:
                self._handle(item)
            except Exception:
                logger.exception("Failed to handle a GSI payload")
            finally:
                self.processed += 1

    def _handle(self, data: dict) -> None:
        snapshot = parse_payload(data)
        if snapshot is None:
            return
        detected = self.detector.update(snapshot)
        now = float(self._clock())
        events = [
            GameEvent(item.type, self.config.priority_for(item.type), dict(item.context))
            for item in detected
        ]
        events.sort(key=lambda event: -event.priority)
        for event in events:
            text = self.lines.select(event, now)
            if not text:
                continue
            logger.info("%s: %s", event.type.value, text)
            self.speech.submit(
                Utterance(event_type=event.type.value, text=text, priority=event.priority)
            )

    def _stdin_loop(self) -> None:
        host, port = self.server_address
        print(
            f"Suit-O is listening on http://{host}:{port}. "
            "Type m and press Enter to mute or unmute. Type q and press Enter to quit.",
            flush=True,
        )
        try:
            for line in sys.stdin:
                command = line.strip().lower()
                if command == "m":
                    muted = self.toggle_mute()
                    print("Muted." if muted else "Listening.", flush=True)
                elif command == "q":
                    self.stop()
                    return
        except Exception:
            logger.debug("Console input ended", exc_info=True)
