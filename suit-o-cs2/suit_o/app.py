"""Wire the GSI server, event detector, line provider, and speech queue."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue

from suit_o.config import Config
from suit_o.events.detector import EventDetector
from suit_o.gsi.parse import parse_payload
from suit_o.gsi.server import GsiServer
from suit_o.lines.provider import LineProvider, YamlLineProvider
from suit_o.models import GameEvent, Utterance
from suit_o.preferences import clamp_volume, save_user_settings
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.devices import (
    list_output_device_names,
    resolve_output_device,
    selectable_playback_names,
)
from suit_o.speech.factory import create_backend
from suit_o.speech.service import SpeechService

logger = logging.getLogger(__name__)

# Spoken by the desktop window's Test voice button. It is not a game event.
TEST_VOICE_LINE = (
    "Helpful tip: if you can hear this, that output device is the one. "
    "I will just stand in the headset."
)

_LOG_LIMIT = 200


@dataclass(frozen=True)
class Activity:
    """One line for the desktop window's scrolling log."""

    seq: int
    at: float
    message: str


@dataclass(frozen=True)
class ListenerSnapshot:
    """Point-in-time state the desktop window paints. No tkinter types."""

    listening: bool
    host: str
    port: int
    muted: bool
    volume: float
    output_device: str
    received: int
    spoken: int
    seconds_since_payload: float | None
    activity: tuple[Activity, ...]


class SuitOApp:
    def __init__(
        self,
        config: Config,
        *,
        backend: SpeechBackend | None = None,
        line_provider: LineProvider | None = None,
        clock=None,
        config_path: Path | None = None,
        output_devices: Callable[[], list[str]] | None = None,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self._output_devices = output_devices
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
        self.last_payload_at: float | None = None
        self._activity: deque[Activity] = deque(maxlen=_LOG_LIMIT)
        self._activity_seq = 0
        self._activity_lock = threading.Lock()

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
        host, port = self.server_address
        self._record(f"Listener up at http://{host}:{port}")
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
        return self.set_muted(not self.muted)

    @property
    def muted(self) -> bool:
        return bool(getattr(self.lines, "muted", False))

    def set_muted(self, muted: bool) -> bool:
        muted = bool(muted)
        if muted == self.muted:
            return muted
        if hasattr(self.lines, "set_muted"):
            self.lines.set_muted(muted)
        else:
            self.lines.muted = muted
        self.speech.set_muted(muted)
        self.config.mute = muted
        self._record("Suit-O is muted" if muted else "Suit-O is listening")
        return muted

    def set_volume(self, volume: float) -> float:
        """Apply Suit-O's own volume, from 0.0 to 1.0. Does not touch the game."""

        applied = clamp_volume(volume)
        self.config.speech.volume = applied
        self.speech.set_volume(applied)
        return applied

    def output_device_names(self) -> list[str]:
        """SAPI playback names, or the injected list used by tests.

        Microphones and virtual cables are removed.
        """

        if self._output_devices is not None:
            listed = list(self._output_devices())
        else:
            listed = list_output_device_names()
        return selectable_playback_names(listed)

    def set_output_device(self, query: str) -> str:
        """Select a playback device and apply it to the next spoken line.

        ``""`` or "Windows default" uses the Windows default endpoint. The
        stored value is the device's full name when the current device list
        contains a match. A microphone name is refused and nothing changes.
        """

        names = self.output_device_names()
        resolved = resolve_output_device(query, names if names else None)
        changed = resolved != self.config.speech.output_device
        self.speech.set_output_device(resolved)
        self.config.speech.output_device = resolved
        if changed:
            if resolved:
                self._record(f"Output device: {resolved}")
            else:
                self._record("Output device: Windows default playback device")
        return resolved

    def test_voice(self, text: str | None = None) -> str:
        """Speak a line on the current device, even when Suit-O is muted."""

        line = (text or TEST_VOICE_LINE).strip()
        if not line:
            raise ValueError("Test voice needs a line to speak")
        self._record(f"test: {line}")
        self.speech.submit(
            Utterance(event_type="test", text=line, priority=100),
            bypass_mute=True,
        )
        return line

    def save_preferences(self) -> None:
        """Write volume, mute, and output device back to the config file."""

        if self.config_path is None:
            raise RuntimeError("Suit-O has no config file to update")
        save_user_settings(
            self.config_path,
            volume=self.config.speech.volume,
            muted=self.muted,
            output_device=self.config.speech.output_device,
        )

    def activity(self) -> tuple[Activity, ...]:
        with self._activity_lock:
            return tuple(self._activity)

    def snapshot(self) -> ListenerSnapshot:
        listening = self._started and not self._did_stop and self._httpd is not None
        host = self.config.server.host
        port = self.config.server.port
        if self._httpd is not None:
            try:
                host, port = self.server_address
            except RuntimeError:
                listening = False
        last = self.last_payload_at
        seconds = None if last is None else max(0.0, time.time() - last)
        return ListenerSnapshot(
            listening=listening,
            host=host,
            port=port,
            muted=self.muted,
            volume=float(self.config.speech.volume),
            output_device=self.config.speech.output_device,
            received=self.processed,
            spoken=len(self.speech.history),
            seconds_since_payload=seconds,
            activity=self.activity(),
        )

    def status(self) -> dict:
        shot = self.snapshot()
        return {
            "muted": shot.muted,
            "received": shot.received,
            "spoken": shot.spoken,
            "listening": shot.listening,
            "volume": shot.volume,
            "output_device": shot.output_device,
            "last_payload_at": self.last_payload_at,
            "seconds_since_payload": shot.seconds_since_payload,
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
            self.last_payload_at = time.time()
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
            self._record(f"{event.type.value}: {text}")
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

    def _record(self, message: str) -> None:
        with self._activity_lock:
            self._activity_seq += 1
            self._activity.append(Activity(self._activity_seq, time.time(), message))
        logger.info("%s", message)
