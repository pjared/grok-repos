"""The Tk helper skips instead of failing when a window cannot be created."""

from __future__ import annotations

import tkinter as tk

import pytest

from tkutil import open_tk_or_skip


def test_tk_helper_skips_when_tcl_cannot_start(monkeypatch):
    def boom():
        raise tk.TclError("Can't find a usable init.tcl")

    monkeypatch.setattr(tk, "Tk", boom)
    with pytest.raises(pytest.skip.Exception):
        open_tk_or_skip()


def test_tk_helper_skips_when_linux_has_no_display(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr("tkutil.sys.platform", "linux")
    with pytest.raises(pytest.skip.Exception):
        open_tk_or_skip()
