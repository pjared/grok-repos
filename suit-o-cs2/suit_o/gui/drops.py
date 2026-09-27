"""File drag-and-drop for the desktop window.

``tkinterdnd2`` bundles the tkdnd extension (XDND on Linux, OLE on Windows).
The Add files button still works when that package is missing.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path


def desktop_root() -> tk.Misc:
    """A Tk root that can receive file drops when tkinterdnd2 is installed."""

    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


def parse_dropped_files(data: str) -> list[Path]:
    """Split a tkdnd file list. Paths with spaces arrive in braces."""

    paths: list[Path] = []
    token: list[str] = []
    brace = False
    for char in data or "":
        if char == "{" and not brace and not token:
            brace = True
            continue
        if char == "}" and brace:
            brace = False
            text = "".join(token).strip()
            if text:
                paths.append(Path(text))
            token = []
            continue
        if char.isspace() and not brace:
            text = "".join(token).strip()
            if text:
                paths.append(Path(text))
            token = []
            continue
        token.append(char)
    text = "".join(token).strip()
    if text:
        paths.append(Path(text))
    return paths


def enable_file_drop(widget: tk.Misc, callback: Callable[[list[Path]], None]) -> bool:
    """Register ``widget`` as a file drop target. False when tkdnd is absent."""

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except ImportError:
        return False
    root = widget.winfo_toplevel()
    try:
        TkinterDnD._require(root)
        widget.drop_target_register(DND_FILES)
    except Exception:
        return False

    def _enter(_event: object) -> str:
        return "copy"

    def _drop(event: object) -> str:
        callback(parse_dropped_files(str(getattr(event, "data", "") or "")))
        return "copy"

    try:
        widget.dnd_bind("<<DropEnter>>", _enter)
        widget.dnd_bind("<<Drop>>", _drop)
    except Exception:
        return False
    return True
