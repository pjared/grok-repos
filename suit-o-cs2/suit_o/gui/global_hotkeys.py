"""Register overlay hotkeys with the OS. Windows only.

RegisterHotKey delivers the chord to this process. Suit-O does not install a
keyboard hook inside CS2 and does not send input back to the game. On other
systems the call is a no-op; the Lineups tab still stores the chords.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes

from suit_o.lineups.hotkeys import Hotkey, parse_hotkey

logger = logging.getLogger(__name__)

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_HWND_MESSAGE = ctypes.c_void_p(-3)

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


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]


class GlobalHotkeys:
    """Background message loop. ``stop`` is safe to call twice."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()

    def start(self, bindings: dict[str, Callable[[], None]]) -> None:
        """Bind canonical labels such as ``ctrl+shift+right`` to callbacks."""

        self.stop()
        if sys.platform != "win32" or not bindings:
            return
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._loop,
            args=(dict(bindings),),
            name="suit-o-hotkeys",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=2)

    def stop(self) -> None:
        thread = self._thread
        thread_id = self._thread_id
        self._thread = None
        self._thread_id = None
        if thread is None or thread_id is None:
            return
        try:
            ctypes.windll.user32.PostThreadMessageW(thread_id, _WM_QUIT, 0, 0)
        except Exception:
            logger.debug("Could not stop the hotkey loop", exc_info=True)
        thread.join(timeout=1)

    def _loop(self, bindings: dict[str, Callable[[], None]]) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        hwnd = user32.CreateWindowExW(
            0,
            "STATIC",
            None,
            0,
            0,
            0,
            0,
            0,
            _HWND_MESSAGE,
            None,
            None,
            None,
        )
        by_id: dict[int, Callable[[], None]] = {}
        for number, (label, callback) in enumerate(bindings.items(), start=1):
            try:
                mods, vk = _win_chord(parse_hotkey(label))
            except Exception:
                logger.exception("Skipping lineup hotkey %s", label)
                continue
            if not user32.RegisterHotKey(hwnd, number, mods | _MOD_NOREPEAT, vk):
                logger.warning("Windows did not register lineup hotkey %s", label)
                continue
            by_id[number] = callback
        self._ready.set()
        message = _MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == _WM_HOTKEY:
                callback = by_id.get(int(message.wParam))
                if callback is not None:
                    try:
                        callback()
                    except Exception:
                        logger.exception("Lineup hotkey failed")
        for ident in by_id:
            user32.UnregisterHotKey(hwnd, ident)
        if hwnd:
            user32.DestroyWindow(hwnd)


def _win_chord(hotkey: Hotkey) -> tuple[int, int]:
    mods = 0
    if "alt" in hotkey.modifiers:
        mods |= _MOD_ALT
    if "ctrl" in hotkey.modifiers:
        mods |= _MOD_CONTROL
    if "shift" in hotkey.modifiers:
        mods |= _MOD_SHIFT
    if "win" in hotkey.modifiers:
        mods |= _MOD_WIN
    key = hotkey.key
    if key in _VK:
        return mods, _VK[key]
    if len(key) == 1 and key.isalpha():
        return mods, ord(key.upper())
    if len(key) == 1 and key.isdigit():
        return mods, ord(key)
    if key.startswith("f") and key[1:].isdigit():
        return mods, 0x70 + int(key[1:]) - 1
    raise ValueError(f"No Windows virtual key for {key!r}")
