"""Parse overlay hotkeys and keep them off the CS2 voice key.

The strings are config text. Registering them with the OS, on Windows, only
wakes this process. Nothing here sends a key into the game.
"""

from __future__ import annotations

from dataclasses import dataclass

_MODIFIERS = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "win",
    "super": "win",
    "meta": "win",
}

_KEYS = {
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
    "space": "space",
    "tab": "tab",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "enter": "enter",
    "esc": "esc",
    "escape": "esc",
}


class HotkeyError(ValueError):
    """A hotkey string is empty, unknown, or collides with another bind."""


@dataclass(frozen=True)
class Hotkey:
    """One chord, already normalized. ``key`` is never a modifier."""

    modifiers: tuple[str, ...]
    key: str

    def label(self) -> str:
        return "+".join((*self.modifiers, self.key))


def parse_hotkey(value: str) -> Hotkey:
    """Turn ``Ctrl + Shift + Right`` into a canonical chord.

    An empty string is refused. Callers that want an unbound action should
    skip parsing.
    """

    parts = [part.strip().lower() for part in value.replace("+", " ").split() if part.strip()]
    if not parts:
        raise HotkeyError("A hotkey cannot be blank")
    modifiers: list[str] = []
    key: str | None = None
    for part in parts:
        if part in _MODIFIERS:
            name = _MODIFIERS[part]
            if name not in modifiers:
                modifiers.append(name)
            continue
        if key is not None:
            raise HotkeyError(f"Hotkey {value!r} has more than one key")
        key = _canonical_key(part)
    if key is None:
        raise HotkeyError(f"Hotkey {value!r} needs a key, not only modifiers")
    order = tuple(name for name in ("ctrl", "alt", "shift", "win") if name in modifiers)
    return Hotkey(modifiers=order, key=key)


def canonical_hotkey(value: str) -> str:
    """Normalized label. Blank stays blank so an action can be unbound."""

    if not value.strip():
        return ""
    return parse_hotkey(value).label()


def assert_distinct(chords: list[str], *, voice_key: str, ptt_key: str) -> None:
    """Refuse a lineup hotkey that matches another lineup hotkey, voice, or PTT.

    Comparison ignores case and spaces. ``ctrl+shift+right`` is not the same
    bind as the voice key ``v``.
    """

    voice = _loose(voice_key)
    ptt = _loose(ptt_key)
    seen: dict[str, str] = {}
    for raw in chords:
        if not raw.strip():
            continue
        label = canonical_hotkey(raw)
        loose = _loose(label)
        if voice and loose == voice:
            raise HotkeyError(
                f"Lineup hotkey {label!r} matches ptt.cs2_voice_key ({voice_key!r}). "
                "Use a different chord so it cannot be Counter-Strike's voice key."
            )
        if ptt and loose == ptt:
            raise HotkeyError(
                f"Lineup hotkey {label!r} matches the reserved ptt.keybind ({ptt_key!r}). "
                "Pick a different chord."
            )
        previous = seen.get(loose)
        if previous is not None:
            raise HotkeyError(
                f"Lineup hotkeys {previous!r} and {label!r} are the same chord. "
                "Next, previous, and hide/show must be different."
            )
        seen[loose] = label


def _canonical_key(part: str) -> str:
    if part in _KEYS:
        return _KEYS[part]
    if len(part) == 1 and part.isalnum():
        return part
    if len(part) >= 2 and part[0] == "f" and part[1:].isdigit():
        number = int(part[1:])
        if 1 <= number <= 12:
            return f"f{number}"
    raise HotkeyError(f"Unknown hotkey {part!r}")


def _loose(value: str) -> str:
    return "".join(value.strip().lower().split())
