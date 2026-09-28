"""Start helper commands without flashing a console window on Windows.

The window runs under ``pythonw``, which has no console. Every console program
it starts (git, pip, ffmpeg) would otherwise open its own Command Prompt window
until it exits. ``CREATE_NO_WINDOW`` gives the child a hidden console instead,
and anything the child starts shares that hidden console.
"""

from __future__ import annotations

import subprocess
import sys


def hidden_window_kwargs(platform: str | None = None) -> dict:
    """Extra ``subprocess`` arguments that keep a child's console hidden."""

    if (platform or sys.platform) != "win32":
        return {}
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return {"creationflags": flag}
