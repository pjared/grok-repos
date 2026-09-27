"""Original 16×16 grenade icons drawn as pixels. Not game assets."""

from __future__ import annotations

import tkinter as tk

# '.' is transparent. Each glyph is 16 by 16.
ICON_ROWS: dict[str, tuple[str, ...]] = {
    "smoke": (
        "................",
        "................",
        "................",
        "......aaa.......",
        "....aabbbba.....",
        "...abbbbbbba....",
        "..abbbccccbbba..",
        "..abbbbbbbbbba..",
        "...abbbbbbbba...",
        "....aabbbbaa....",
        "......aaaa......",
        "................",
        "................",
        "................",
        "................",
        "................",
    ),
    "flash": (
        "................",
        ".......w........",
        "......ywy.......",
        "...y...w...y....",
        "....y.ywy.y.....",
        ".....yywyy......",
        "..y.yyywyyy.y...",
        ".yyyyyywyyyyyy..",
        "..y.yyywyyy.y...",
        ".....yywyy......",
        "....y.ywy.y.....",
        "...y...w...y....",
        "......ywy.......",
        ".......w........",
        "................",
        "................",
    ),
    "molotov": (
        "................",
        ".......r........",
        "......ryr.......",
        "......ryr.......",
        ".....ryyyr......",
        ".....rooor......",
        "....roooor......",
        "....roooor......",
        "...roooooor.....",
        "...roooooor.....",
        "..roooooooor....",
        "..oooooooooo....",
        "...oooooooo.....",
        "....oooooo......",
        "................",
        "................",
    ),
    "he": (
        "................",
        "......ssss......",
        ".....s....s.....",
        "......ssss......",
        "....gggggggg....",
        "...gggggggggg...",
        "..ggghhgggggg...",
        "..gggggggggggg..",
        "..gggggggggggg..",
        "..gggggggggggg..",
        "...gggggggggg...",
        "...gggggggggg...",
        "....gggggggg....",
        ".....gggggg.....",
        "................",
        "................",
    ),
}

_COLORS = {
    "smoke": {"a": "#9aa1a8", "b": "#d5d8dc", "c": "#f7f8f8"},
    "flash": {"y": "#f5c518", "w": "#fff6c2"},
    "molotov": {"o": "#e85d04", "r": "#ffd60a"},
    "he": {"g": "#1b4332", "h": "#95d5b2", "s": "#d8d8d8"},
}


def grenade_icons(master: tk.Misc) -> dict[str, tk.PhotoImage]:
    """One PhotoImage per grenade. Keep the dict alive or Tk drops the pixels."""

    return {name: _draw(master, ICON_ROWS[name], _COLORS[name]) for name in ICON_ROWS}


def _draw(master: tk.Misc, rows: tuple[str, ...], colors: dict[str, str]) -> tk.PhotoImage:
    image = tk.PhotoImage(master=master, width=len(rows[0]), height=len(rows))
    for y, row in enumerate(rows):
        for x, pixel in enumerate(row):
            color = colors.get(pixel)
            if color:
                image.put(color, (x, y))
    return image
