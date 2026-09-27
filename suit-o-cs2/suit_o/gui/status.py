"""Text for the desktop window. No tkinter imports, so tests can run headless."""

from __future__ import annotations

import time

from suit_o.app import Activity
from suit_o.config import ConfigError
from suit_o.speech.devices import (
    WINDOWS_DEFAULT_LABEL,
    DeviceSelectionError,
    resolve_output_device,
)

# CS2's GSI heartbeat in the shipped cfg is 30 seconds. A little past that
# still counts as "the game is sending state."
FRESH_PAYLOAD_SECONDS = 45.0

_TONE_COLOR = {
    "ok": "#1b7f3a",
    "wait": "#666666",
    "stale": "#b86e00",
    "down": "#b00020",
    "muted": "#b86e00",
}


def tone_color(tone: str) -> str:
    return _TONE_COLOR.get(tone, _TONE_COLOR["wait"])


def format_age(seconds: float) -> str:
    """Short age for a status line, such as ``3s`` or ``2m 5s``."""

    whole = max(0, int(seconds))
    if whole < 60:
        return f"{whole}s"
    minutes, secs = divmod(whole, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def format_listener(listening: bool, host: str, port: int) -> tuple[str, str]:
    if listening:
        return f"Listener up · http://{host}:{port}", "ok"
    return "Listener stopped", "down"


def format_game_state(
    seconds_since: float | None,
    *,
    received: int = 0,
    fresh_seconds: float = FRESH_PAYLOAD_SECONDS,
) -> tuple[str, str]:
    """Return ``(label, tone)`` for whether CS2 is posting game state."""

    if seconds_since is None:
        return "Waiting for CS2", "wait"
    age = format_age(seconds_since)
    if seconds_since <= fresh_seconds:
        text = f"CS2 is sending game state · last payload {age} ago"
        tone = "ok"
    else:
        text = f"No recent game state · last payload {age} ago"
        tone = "stale"
    if received:
        text += f" · {received} received"
    return text, tone


def format_sound(muted: bool) -> tuple[str, str]:
    if muted:
        return "Muted", "muted"
    return "Sound on", "ok"


def format_activity(entry: Activity) -> str:
    clock = time.strftime("%H:%M:%S", time.localtime(entry.at))
    return f"{clock}  {entry.message}"


def device_menu_labels(names: list[str], current: str) -> list[str]:
    """Dropdown labels. The Windows default is first. Microphones stay out.

    ``current`` is appended when it is a saved name the live list does not
    have, so the window does not hide a device that is unplugged.
    """

    labels = [WINDOWS_DEFAULT_LABEL]
    for name in names:
        if name and name not in labels:
            labels.append(name)
    if current and current not in labels:
        labels.append(current)
    return labels


def selected_device_label(current: str, names: list[str]) -> str:
    """Label to show for the saved output device."""

    if not current:
        return WINDOWS_DEFAULT_LABEL
    try:
        resolved = resolve_output_device(current, names if names else None)
    except (ConfigError, DeviceSelectionError):
        return current
    if not resolved:
        return WINDOWS_DEFAULT_LABEL
    return resolved
