"""Chat push-to-talk. This chord is not CS2's voice key.

The default is F8. ``ptt.cs2_voice_key`` is whatever the player says their
in-game voice bind is. When that value is set and the two chords match,
chat shows a warning. An empty voice key is not detectable, so there is
nothing to warn about.
"""

from __future__ import annotations

import sys

from suit_o.lineups.hotkeys import HotkeyError, canonical_hotkey, parse_hotkey

DEFAULT_CHAT_PTT = "f8"

_VK = {
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "space": 0x20,
    "tab": 0x09,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "enter": 0x0D,
    "esc": 0x1B,
}


class PttMonitor:
    """Turn a held key into one down edge and one up edge."""

    def __init__(self) -> None:
        self.held = False

    def poll(self, pressed: bool) -> str | None:
        if pressed and not self.held:
            self.held = True
            return "down"
        if not pressed and self.held:
            self.held = False
            return "up"
        return None


def normalize_ptt_key(value: str) -> str:
    """Canonical chord, or ``""`` when the box is empty. Unknown text is refused."""

    if not str(value or "").strip():
        return ""
    return canonical_hotkey(str(value))


def keys_conflict(chat_key: str, voice_key: str) -> bool:
    """True when both chords are known and they are the same bind."""

    voice = str(voice_key or "").strip()
    chat = str(chat_key or "").strip()
    if not voice or not chat:
        return False
    try:
        return _loose(canonical_hotkey(chat)) == _loose(canonical_hotkey(voice))
    except HotkeyError:
        return False


def voice_key_warning(chat_key: str, voice_key: str) -> str:
    if not keys_conflict(chat_key, voice_key):
        return ""
    shown = str(chat_key or "").strip()
    try:
        shown = canonical_hotkey(shown)
    except HotkeyError:
        pass
    return (
        f"Chat push-to-talk is {shown}, the same key as CS2 voice ({str(voice_key).strip()}). "
        "Pick a different chat.ptt_key so holding it does not open CS2 voice chat."
    )


def key_is_down(label: str) -> bool:
    """True while the chord is physically held. Other systems report false.

    Windows is polled with GetAsyncKeyState. Suit-O does not send the key
    back to the game.
    """

    if sys.platform != "win32" or not str(label or "").strip():
        return False
    try:
        hotkey = parse_hotkey(label)
        vk = _virtual_key(hotkey.key)
    except (HotkeyError, ValueError, OSError):
        return False
    try:
        import ctypes
    except ImportError:
        return False
    user32 = ctypes.windll.user32

    def down(code: int) -> bool:
        return bool(user32.GetAsyncKeyState(code) & 0x8000)

    if not down(vk):
        return False
    wanted = set(hotkey.modifiers)
    pairs = (
        ("ctrl", 0x11),
        ("alt", 0x12),
        ("shift", 0x10),
        ("win", 0x5B),
    )
    for name, code in pairs:
        held = down(code)
        if name == "win":
            held = held or down(0x5C)
        if held != (name in wanted):
            return False
    return True


def _virtual_key(key: str) -> int:
    if key in _VK:
        return _VK[key]
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and key.isdigit():
        return ord(key)
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 12:
            return 0x70 + number - 1
    raise ValueError(f"No virtual key for {key!r}")


def _loose(value: str) -> str:
    return "".join(value.strip().lower().split())
