"""Debounced file watching and the in-place GUI restart.

Content files (config, lines, voices, lineups) reload in the running process.
Python files under ``suit_o`` restart the process once, after a short quiet
period, so a multi-file ``git pull`` does not relaunch per file.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from suit_o.config import DEFAULT_CONFIG_PATH
from suit_o.local_config import local_config_path

RESTART_STATE_NAME = ".suit-o-restart.json"
ACTIVITY_HANDOFF_NAME = "suit-o-activity-handoff.json"
ACTIVITY_HANDOFF_LIMIT = 200


@dataclass
class RestartState:
    x: int
    y: int
    width: int
    height: int
    tab: int
    notice: str


class ChangeDebouncer:
    """Collect change kinds until ``delay`` seconds after the latest note."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._kinds: set[str] = set()
        self._deadline: float | None = None

    def note(self, kind: str, now: float) -> None:
        self._kinds.add(kind)
        self._deadline = now + self.delay

    def ready(self, now: float) -> list[str] | None:
        if self._deadline is None or now < self._deadline:
            return None
        kinds = sorted(self._kinds)
        self._kinds.clear()
        self._deadline = None
        return kinds


def restart_is_blocked(activity: str | None, round_phase: str | None) -> bool:
    """True only during a live round outside the main menu.

    No game state yet does not block. Freezetime, overtime end, warmup, and
    the menu all allow a process restart. Content can still reload while a
    round is live; this only gates a restart and the Update button.
    """

    if (activity or "").strip().lower() == "menu":
        return False
    return (round_phase or "").strip().lower() == "live"


def choose_reload(kinds: list[str]) -> str:
    """A code change restarts once. That restart also picks up content edits."""

    if "code" in kinds:
        return "restart"
    if "content" in kinds:
        return "reload"
    return "none"


def change_kind(
    path: Path,
    *,
    root: Path,
    config_path: Path,
    lines_path: Path | None,
) -> str | None:
    """Classify one file. ``None`` means the watcher should ignore it."""

    resolved = path.resolve()
    if resolved.suffix == ".pyc" or "__pycache__" in resolved.parts:
        return None
    config_dir = Path(config_path).resolve().parent
    if resolved.parent == config_dir and resolved.name in {"config.yaml", "config.local.yaml"}:
        return "content"
    if lines_path is not None and resolved == Path(lines_path).resolve():
        return "content"
    try:
        relative = resolved.relative_to(Path(root).resolve())
    except ValueError:
        return None
    if not relative.parts:
        return None
    top = relative.parts[0]
    if top == "suit_o" and resolved.suffix == ".py":
        return "code"
    if top in {"lines", "voices", "lineups"}:
        return "content"
    return None


class FileWatcher:
    """Poll mtimes. The first scan only records them. Pass ``now`` in tests."""

    def __init__(
        self,
        root: Path,
        *,
        config_path: Path,
        lines_path: Path | None,
        delay: float = 0.6,
    ) -> None:
        self.root = Path(root)
        self.config_path = Path(config_path)
        self.lines_path = None if lines_path is None else Path(lines_path)
        self._debouncer = ChangeDebouncer(delay)
        self._seen: dict[Path, int] = {}
        self._primed = False
        self._quiet: dict[Path, float] = {}

    def ignore(self, path: Path, until: float) -> None:
        """Skip notes for ``path`` until ``until``. The new mtime is absorbed."""

        self._quiet[Path(path).resolve()] = until

    def scan(self, now: float) -> list[str] | None:
        current: dict[Path, int] = {}
        for path in self._files():
            try:
                current[path.resolve()] = path.stat().st_mtime_ns
            except OSError:
                continue
        if not self._primed:
            self._seen = current
            self._primed = True
            return None
        changed = [
            path for path, stamp in current.items() if self._seen.get(path) != stamp
        ]
        changed.extend(path for path in self._seen if path not in current)
        self._seen = current
        for path in changed:
            if now < self._quiet.get(path, 0.0):
                continue
            kind = change_kind(
                path,
                root=self.root,
                config_path=self.config_path,
                lines_path=self.lines_path,
            )
            if kind:
                self._debouncer.note(kind, now)
        return self._debouncer.ready(now)

    def _files(self) -> list[Path]:
        found = [self.config_path, local_config_path(self.config_path)]
        if self.lines_path is not None:
            found.append(self.lines_path)
        for folder in ("lines", "voices", "lineups", "suit_o"):
            base = self.root / folder
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                if "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                found.append(path)
        return found


def restart_state_path(config_path: Path) -> Path:
    return Path(config_path).with_name(RESTART_STATE_NAME)


def write_restart_state(config_path: Path, state: RestartState) -> None:
    path = restart_state_path(config_path)
    payload = {
        "x": int(state.x),
        "y": int(state.y),
        "width": max(1, int(state.width)),
        "height": max(1, int(state.height)),
        "tab": int(state.tab),
        "notice": state.notice,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def consume_restart_state(config_path: Path) -> RestartState | None:
    """Return the saved window state once, then delete the file."""

    path = restart_state_path(config_path)
    if not path.is_file():
        return None
    state: RestartState | None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        state = RestartState(
            x=int(raw["x"]),
            y=int(raw["y"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
            tab=int(raw["tab"]),
            notice=str(raw.get("notice") or "Reloaded"),
        )
    except (OSError, ValueError, KeyError, TypeError):
        state = None
    try:
        path.unlink()
    except OSError:
        pass
    return state


def activity_handoff_path() -> Path:
    """Temp file for the in-window log. It is not a saved log."""

    return Path(tempfile.gettempdir()) / ACTIVITY_HANDOFF_NAME


def write_activity_handoff(entries: Sequence[tuple[float, str]], *, secret: str = "") -> Path:
    """Leave the current log lines where the replacement process can read them.

    The file lives in the OS temp directory. The new process deletes it as
    soon as it has read the lines.
    """

    path = activity_handoff_path()
    hidden = secret.strip()
    payload_entries = []
    for at, message in list(entries)[-ACTIVITY_HANDOFF_LIMIT:]:
        text = str(message)
        if hidden:
            text = text.replace(hidden, "[redacted]")
        payload_entries.append({"at": float(at), "message": text})
    raw = json.dumps({"entries": payload_entries}).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return path


def consume_activity_handoff() -> list[tuple[float, str]]:
    """Read the carried log lines once, then delete the temp file."""

    path = activity_handoff_path()
    if not path.is_file():
        return []
    entries: list[tuple[float, str]] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("entries") if isinstance(raw, dict) else None
        if isinstance(items, list):
            for item in items[-ACTIVITY_HANDOFF_LIMIT:]:
                if not isinstance(item, dict):
                    continue
                message = item.get("message")
                at = item.get("at")
                if not isinstance(message, str) or isinstance(at, bool) or not isinstance(at, (int, float)):
                    continue
                entries.append((float(at), message))
    except (OSError, ValueError, TypeError):
        entries = []
    try:
        path.unlink()
    except OSError:
        pass
    return entries


def gui_restart_argv(config_path: Path | None) -> list[str]:
    """Command line for the replacement process. Mute stays in the local file."""

    argv = [sys.executable, "-m", "suit_o.gui"]
    if config_path is not None and Path(config_path).resolve() != DEFAULT_CONFIG_PATH.resolve():
        argv.extend(["--config", str(config_path)])
    return argv
