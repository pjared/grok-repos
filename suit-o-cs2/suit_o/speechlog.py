"""Daily speech log. Spoken lines, skips, and payload notes are appended as JSONL.

One file per local day lives in ``logs/``, which git ignores. Files older
than ``keep_days`` are deleted. The GSI auth token is never written. A raw
payload is not written either.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_NAME = re.compile(r"^speech-(\d{4}-\d{2}-\d{2})\.jsonl$")


@dataclass(frozen=True)
class SpeechLogEntry:
    """One spoken line, or a detected event that was not spoken."""

    at: float
    event: str
    text: str
    status: str
    map_name: str
    round_number: int | None
    voice: str
    kind: str = "line"


@dataclass(frozen=True)
class PayloadMinute:
    """How many accepted GSI posts arrived during one local minute."""

    minute: str
    count: int
    first: str
    last: str


def redact(value: str, secrets: tuple[str, ...]) -> str:
    """Replace any configured secret, including the GSI auth token, with a marker."""

    cleaned = value
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


class SpeechLog:
    """Append-only daily files. Pruning uses the date in the file name."""

    def __init__(
        self,
        directory: Path,
        keep_days: int,
        *,
        now=None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        if isinstance(keep_days, bool) or not isinstance(keep_days, int) or keep_days < 1:
            raise ValueError("logs.keep_days must be a positive integer")
        self.directory = Path(directory)
        self.keep_days = keep_days
        self.secrets = secrets
        self._now = now or time.time
        self._lock = threading.Lock()
        self._open_minute: str | None = None
        self._open_count = 0
        self._open_first = 0.0
        self._open_last = 0.0

    def append(self, entry: SpeechLogEntry) -> Path:
        """Write one JSON object and drop daily files that are past ``keep_days``."""

        local = time.localtime(entry.at)
        payload = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", local),
            "kind": entry.kind,
            "event": entry.event,
            "text": entry.text.replace("\r", " ").replace("\n", " "),
            "status": entry.status,
            "map": entry.map_name,
            "round": entry.round_number,
            "voice": entry.voice,
        }
        with self._lock:
            return self._write(payload, entry.at)

    def note_payload(self, at: float) -> PayloadMinute | None:
        """Count one accepted post. The previous minute is written when the clock rolls."""

        minute = time.strftime("%Y-%m-%dT%H:%M", time.localtime(at))
        with self._lock:
            if self._open_minute is None:
                self._open_minute = minute
                self._open_count = 1
                self._open_first = at
                self._open_last = at
                return None
            if minute == self._open_minute:
                self._open_count += 1
                self._open_last = at
                return None
            finished = self._finish_minute()
            self._open_minute = minute
            self._open_count = 1
            self._open_first = at
            self._open_last = at
            return finished

    def note_rejected(self, at: float, reason: str) -> Path:
        """Record why a post was refused. ``reason`` must not include the token."""

        local = time.localtime(at)
        payload = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", local),
            "kind": "rejected",
            "event": "gsi",
            "text": "",
            "status": reason,
            "map": "",
            "round": None,
            "voice": "",
        }
        with self._lock:
            return self._write(payload, at)

    def flush(self) -> PayloadMinute | None:
        """Write the open minute, if any posts are still uncounted on disk."""

        with self._lock:
            if self._open_minute is None:
                return None
            return self._finish_minute()

    def _finish_minute(self) -> PayloadMinute:
        first = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._open_first))
        last = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._open_last))
        minute = self._open_minute or ""
        count = self._open_count
        payload = {
            "time": last,
            "kind": "payload",
            "event": "gsi",
            "text": "",
            "status": "received",
            "map": "",
            "round": None,
            "voice": "",
            "count": count,
            "first": first,
            "last": last,
        }
        self._write(payload, self._open_last)
        self._open_minute = None
        self._open_count = 0
        return PayloadMinute(minute=minute, count=count, first=first, last=last)

    def _write(self, payload: dict, at: float) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d", time.localtime(at))
        path = self.directory / f"speech-{day}.jsonl"
        safe = _redact_payload(payload, self.secrets)
        line = json.dumps(safe, ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        self.prune()
        return path

    def prune(self, today: date | None = None) -> list[Path]:
        """Delete ``speech-YYYY-MM-DD.jsonl`` files that are ``keep_days`` or older."""

        if not self.directory.is_dir():
            return []
        current = today or datetime.fromtimestamp(float(self._now())).date()
        removed: list[Path] = []
        for path in self.directory.iterdir():
            match = _NAME.match(path.name)
            if match is None or not path.is_file():
                continue
            try:
                written = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if (current - written).days >= self.keep_days:
                path.unlink()
                removed.append(path)
        return removed


def _redact_payload(payload: dict, secrets: tuple[str, ...]) -> dict:
    safe: dict = {}
    for key, value in payload.items():
        if isinstance(value, str):
            safe[key] = redact(value, secrets)
        else:
            safe[key] = value
    return safe


def open_log_folder(path: Path) -> None:
    """Open ``path`` in the system file browser. Creates it if needed."""

    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606 - the player's own log folder
        return
    command = ["open", str(folder)] if sys.platform == "darwin" else ["xdg-open", str(folder)]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
