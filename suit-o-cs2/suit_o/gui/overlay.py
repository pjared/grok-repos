"""Always-on-top lineup window. It does not take clicks or keyboard focus.

On Windows the extended style WS_EX_TRANSPARENT makes clicks fall through to
whatever is underneath, which is CS2 when the game is borderless or windowed.
The window never injects into the game and never sends input.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import tkinter as tk

from suit_o.app import SuitOApp
from suit_o.gui.grenade_icons import grenade_icons
from suit_o.lineups.library import LineupCard
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
        self._aim_photo: tk.PhotoImage | None = None
        self._shown_path = ""
        self._shown_aim = ""
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
        self._icons = grenade_icons(self.top)
        self.photos = tk.Frame(self.top, bg="#1b1b1b")
        self.photos.pack()
        self.image = tk.Label(self.photos, bg="#1b1b1b", bd=0)
        self.image.pack(side="left")
        self.aim = tk.Label(self.photos, bg="#1b1b1b", bd=0)
        self.caption_row = tk.Frame(self.top, bg="#1b1b1b")
        self.caption_row.pack(fill="x")
        self.icon = tk.Label(self.caption_row, bg="#1b1b1b", bd=0)
        self.icon.pack(side="left", padx=(8, 0))
        self.caption = tk.Label(
            self.caption_row,
            bg="#1b1b1b",
            fg="#f2f2f2",
            wraplength=320,
            justify="center",
            padx=8,
            pady=4,
        )
        self.caption.pack(side="left", fill="x", expand=True)
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
            self._shown_aim = ""
            self._shown_width = 0
            return
        card = view.card
        width = int(settings.width)
        slots = overlay_images(card, width)
        signature = tuple((str(path), slot_width) for path, slot_width in slots)
        if (self._shown_path, self._shown_aim, self._shown_width) != (
            signature[0][0] if signature else "",
            signature[1][0] if len(signature) > 1 else "",
            width,
        ):
            self._photo = _fit_photo(str(slots[0][0]), slots[0][1])
            self.image.configure(image=self._photo)
            if len(slots) > 1:
                self._aim_photo = _fit_photo(str(slots[1][0]), slots[1][1])
                self.aim.configure(image=self._aim_photo)
                self.aim.pack(side="left")
            else:
                self._aim_photo = None
                self.aim.pack_forget()
            self._shown_path = signature[0][0]
            self._shown_aim = signature[1][0] if len(signature) > 1 else ""
            self._shown_width = width
        icon = self._icons.get(card.grenade)
        if icon is None:
            self.icon.pack_forget()
        else:
            self.icon.configure(image=icon)
            self.icon.pack(side="left", padx=(8, 0))
        self.caption.configure(text=f"{card.caption}  ({view.index + 1}/{view.total})", wraplength=max(1, width - 24))
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


def overlay_images(card: LineupCard, width: int) -> list[tuple[Path, int]]:
    """Stand photo, plus the aim photo beside it when the pack supplied one."""

    total = max(1, int(width))
    if card.aim_path is not None:
        stand_width = max(1, total // 2)
        return [(card.path, stand_width), (card.aim_path, max(1, total - stand_width))]
    return [(card.path, total)]


def _fit_photo(path: str, max_width: int) -> tk.PhotoImage:
    from suit_o.gui.photos import fit_photo

    return fit_photo(path, max_width)


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
