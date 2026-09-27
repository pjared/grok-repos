"""Open a Tk window in tests, or skip when this machine has no display."""

from __future__ import annotations

import os
import sys

import pytest


def open_tk_or_skip():
    """Return a withdrawn Tk root. Skip if Tcl cannot create a window."""

    import tkinter as tk

    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        pytest.skip("no display for Tk")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk could not open a window: {exc}")
    root.withdraw()
    return root
