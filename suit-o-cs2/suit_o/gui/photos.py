"""Lineup photos. PNG uses Tk. JPEG and WebP need Pillow."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

_TK_SUFFIXES = {".png", ".gif", ".ppm", ".pgm"}


def fit_photo(path: str, max_width: int, max_height: int | None = None) -> tk.PhotoImage:
    """Load a lineup photo and fit it inside the given size, keeping the aspect ratio."""

    if max_height is not None:
        return _fit_inside(path, max_width, max_height)
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


def _fit_inside(path: str, max_width: int, max_height: int) -> tk.PhotoImage:
    width = max(1, int(max_width))
    height = max(1, int(max_height))
    try:
        from PIL import Image, ImageTk
    except ImportError as exc:
        try:
            return _subsample_box(tk.PhotoImage(file=path), width, height)
        except tk.TclError:
            raise tk.TclError(f"Could not open {Path(path).name}. Install Pillow.") from exc
    try:
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
            image.thumbnail((width, height))
            return ImageTk.PhotoImage(image)
    except (OSError, ValueError) as exc:
        raise tk.TclError(f"Could not open {Path(path).name}.") from exc


def _subsample_box(image: tk.PhotoImage, max_width: int, max_height: int) -> tk.PhotoImage:
    factor = 1
    while factor < 16 and (
        image.width() // factor > max_width or image.height() // factor > max_height
    ):
        factor += 1
    if factor == 1:
        return image
    return image.subsample(factor, factor)


def _subsample(image: tk.PhotoImage, max_width: int) -> tk.PhotoImage:
    factor = 1
    while factor < 8 and image.width() // factor > max_width:
        factor += 1
    if factor == 1:
        return image
    return image.subsample(factor, factor)
