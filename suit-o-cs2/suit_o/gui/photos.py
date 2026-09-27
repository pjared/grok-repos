"""Lineup photos. PNG uses Tk. JPEG and WebP need Pillow."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

_TK_SUFFIXES = {".png", ".gif", ".ppm", ".pgm"}


def fit_photo(path: str, max_width: int) -> tk.PhotoImage:
    """Load a lineup photo and fit it to ``max_width`` pixels."""

    width = max(1, int(max_width))
    suffix = Path(path).suffix.lower()
    if suffix in _TK_SUFFIXES:
        try:
            return _subsample(tk.PhotoImage(file=path), width)
        except tk.TclError:
            pass
    try:
        from PIL import Image, ImageTk
    except ImportError as exc:
        raise tk.TclError(f"Could not open {Path(path).name}. Install Pillow.") from exc
    try:
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
            if image.width > width:
                height = max(1, round(image.height * width / max(image.width, 1)))
                image = image.resize((width, height))
            return ImageTk.PhotoImage(image)
    except (OSError, ValueError) as exc:
        raise tk.TclError(f"Could not open {Path(path).name}.") from exc


def _subsample(image: tk.PhotoImage, max_width: int) -> tk.PhotoImage:
    factor = 1
    while factor < 8 and image.width() // factor > max_width:
        factor += 1
    if factor == 1:
        return image
    return image.subsample(factor, factor)
