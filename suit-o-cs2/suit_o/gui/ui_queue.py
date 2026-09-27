"""Run UI work on the Tk thread. Workers only enqueue callables."""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable

logger = logging.getLogger(__name__)


class UiQueue:
    """A queue drained by ``after`` on the widget that owns the window."""

    def __init__(self) -> None:
        self._items: queue.Queue[Callable[[], None]] = queue.Queue()
        self._widget: tk.Misc | None = None

    def bind(self, widget: tk.Misc) -> None:
        self._widget = widget
        self._pump()

    def call(self, callback: Callable[[], None]) -> None:
        """Schedule ``callback``. Safe to call from a worker thread."""

        self._items.put(callback)

    def drain(self) -> None:
        """Run queued work. One failure is logged and the rest still run."""

        while True:
            try:
                callback = self._items.get_nowait()
            except queue.Empty:
                return
            try:
                callback()
            except Exception:
                logger.exception("UI update failed")

    def _pump(self) -> None:
        widget = self._widget
        if widget is None:
            return
        self.drain()
        try:
            widget.after(30, self._pump)
        except tk.TclError:
            return
