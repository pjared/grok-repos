"""Lineup photos. JPEG and WebP need Pillow; PNG can use Tk."""

from __future__ import annotations

from pathlib import Path

from suit_o.gui.photos import fit_photo
from tkutil import open_tk_or_skip


def test_jpeg_and_webp_lineup_photos_fit(tmp_path: Path):
    from PIL import Image

    root = open_tk_or_skip()
    try:
        for suffix in (".jpg", ".webp", ".png"):
            path = tmp_path / f"stand{suffix}"
            Image.new("RGB", (40, 20), (10, 20, 30)).save(path)
            photo = fit_photo(str(path), 16)
            assert 1 <= photo.width() <= 16
            assert photo.height() >= 1
    finally:
        root.destroy()
