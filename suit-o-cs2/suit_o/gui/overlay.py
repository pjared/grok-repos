"""Always-on-top lineup window. It does not take clicks or keyboard focus.

On Windows the extended style WS_EX_TRANSPARENT makes clicks fall through to
whatever is underneath, which is CS2 when the game is borderless or windowed.
The window never injects into the game and never sends input.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk

from suit_o.app import SuitOApp
from suit_o.lineups.place import Monitor, pick_monitor, place_overlay

logger = logging.getLogger(__name__)

_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_NOACTIVATE = 0x08000000
_GWL_EXSTYLE = -20


class LineupOverlay:
    """Paints the current card. The deck decides whether it should be visible."""

    def __init__(self, owner: tk.Tk, app: SuitOApp, monitors) -> None:
        self._owner = owner
        self.app = app
        self._monitors = monitors
        self._closed = False
        self._photo: tk.PhotoImage | None = None
        self._shown_path = ""
        self._shown_width = 0
        self._job: str | None = None

        self.top = tk.Toplevel(owner)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="#1b1b1b")
        try:
            self.top.attributes("-alpha", float(app.config.lineups.opacity))
        except tk.TclError:
            logger.debug("This display cannot set window opacity", exc_info=True)
        self.image = tk.Label(self.top, bg="#1b1b1b", bd=0)
        self.image.pack()
        self.caption = tk.Label(
            self.top,
            bg="#1b1b1b",
            fg="#f2f2f2",
            wraplength=320,
            justify="center",
            padx=8,
            pady=4,
        )
        self.caption.pack(fill="x")
        self.top.bind("<FocusIn>", self._refuse_focus)
        self.top.withdraw()
        self._job = self.top.after(200, self.refresh)

    def refresh(self) -> None:
        if self._closed:
            return
        try:
            self._paint()
        except Exception:
            logger.exception("Could not paint the lineup overlay")
        self._job = self.top.after(200, self.refresh)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._job is not None:
            try:
                self.top.after_cancel(self._job)
            except tk.TclError:
                pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def _paint(self) -> None:
        view = self.app.lineup_view()
        settings = self.app.config.lineups
        if not view.visible or view.card is None:
            if self.top.winfo_viewable():
                self.top.withdraw()
            self._shown_path = ""
            self._shown_width = 0
            return
        card = view.card
        width = int(settings.width)
        if self._shown_path != str(card.path) or self._shown_width != width:
            self._photo = _fit_photo(str(card.path), width)
            self.image.configure(image=self._photo)
            self._shown_path = str(card.path)
            self._shown_width = width
        self.caption.configure(text=f"{card.caption}  ({view.index + 1}/{view.total})", wraplength=width)
        try:
            self.top.attributes("-alpha", float(settings.opacity))
        except tk.TclError:
            pass
        self.top.update_idletasks()
        monitors = self._monitors()
        monitor = pick_monitor(monitors, settings.monitor)
        width_px = max(1, int(self.top.winfo_reqwidth()))
        height_px = max(1, int(self.top.winfo_reqheight()))
        x, y = place_overlay(monitor, settings.corner, width_px, height_px)
        self.top.geometry(f"{width_px}x{height_px}+{x}+{y}")
        if not self.top.winfo_viewable():
            self.top.deiconify()
            self.top.attributes("-topmost", True)
            _make_click_through(self.top)
            self._refuse_focus(None)

    def _refuse_focus(self, _event: object) -> None:
        try:
            self._owner.focus_set()
        except tk.TclError:
            pass


def monitors_for(owner: tk.Misc) -> list[Monitor]:
    """Displays Suit-O can pin the overlay to. Index 0 is the primary."""

    if sys.platform == "win32":
        found = _windows_monitors()
        if found:
            return found
    return [
        Monitor(
            0,
            0,
            0,
            int(owner.winfo_screenwidth()),
            int(owner.winfo_screenheight()),
            "Primary",
        )
    ]


def _fit_photo(path: str, max_width: int) -> tk.PhotoImage:
    image = tk.PhotoImage(file=path)
    factor = 1
    while factor < 8 and image.width() // factor > max_width:
        factor += 1
    if factor == 1:
        return image
    return image.subsample(factor, factor)


def _make_click_through(window: tk.Toplevel) -> None:
    """Let clicks pass through on Windows. Other systems keep the window unfocused."""

    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes_hwnd(window)
        user32 = __import__("ctypes").windll.user32
        style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd,
            _GWL_EXSTYLE,
            style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_NOACTIVATE,
        )
    except Exception:
        logger.debug("Could not mark the overlay click-through", exc_info=True)


def ctypes_hwnd(window: tk.Toplevel) -> int:
    import ctypes

    return int(ctypes.windll.user32.GetParent(window.winfo_id()))


def _windows_monitors() -> list[Monitor]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    monitors: list[Monitor] = []

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def _each(_monitor, _hdc, rect, _data) -> int:
        box = rect.contents
        index = len(monitors)
        monitors.append(
            Monitor(
                index,
                int(box.left),
                int(box.top),
                int(box.right - box.left),
                int(box.bottom - box.top),
                f"Display {index + 1}",
            )
        )
        return 1

    user32.EnumDisplayMonitors(None, None, callback_type(_each), 0)
    return monitors
