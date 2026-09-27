"""Daily speech log. Spoken lines and skips are appended as JSONL.

One file per local day lives in ``logs/``, which git ignores. Files older
than ``keep_days`` are deleted. The token and raw game payloads are not written.
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
    """One spoken line, or one line that mute or a cooldown held back."""

    at: float
    event: str
    text: str
    status: str
    map_name: str
    round_number: int | None
    voice: str


class SpeechLog:
    """Append-only daily files. Pruning uses the date in the file name."""

    def __init__(self, directory: Path, keep_days: int, *, now=None) -> None:
        if isinstance(keep_days, bool) or not isinstance(keep_days, int) or keep_days < 1:
            raise ValueError("logs.keep_days must be a positive integer")
        self.directory = Path(directory)
        self.keep_days = keep_days
        self._now = now or time.time
        self._lock = threading.Lock()

    def append(self, entry: SpeechLogEntry) -> Path:
        """Write one JSON object and drop daily files that are past ``keep_days``."""

        self.directory.mkdir(parents=True, exist_ok=True)
        local = time.localtime(entry.at)
        day = time.strftime("%Y-%m-%d", local)
        path = self.directory / f"speech-{day}.jsonl"
        payload = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", local),
            "event": entry.event,
            "text": entry.text.replace("\r", " ").replace("\n", " "),
            "status": entry.status,
            "map": entry.map_name,
            "round": entry.round_number,
            "voice": entry.voice,
        }
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._lock:
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


def open_log_folder(path: Path) -> None:
    """Open ``path`` in the system file browser. Creates it if needed."""

    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606 - the player's own log folder
        return
    command = ["open", str(folder)] if sys.platform == "darwin" else ["xdg-open", str(folder)]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
