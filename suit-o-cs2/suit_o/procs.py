"""Start helper commands without flashing a console window on Windows.

The window runs under ``pythonw``, which has no console. Every console program
it starts (git, pip, ffmpeg) would otherwise open its own Command Prompt window
until it exits. ``CREATE_NO_WINDOW`` gives the child a hidden console instead,
and anything the child starts shares that hidden console.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def hidden_window_kwargs(platform: str | None = None) -> dict:
    """Extra ``subprocess`` arguments that keep a child's console hidden."""

    if (platform or sys.platform) != "win32":
        return {}
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return {"creationflags": flag}


def launch_setup(script, *, popen=None) -> None:
    """Open the setup script in its own visible window, detached from Suit-O.

    Setup is long and shows its progress, so this is the one window Suit-O
    opens on purpose. ``cmd /c start`` gives the script its own console that
    outlives Suit-O, which the script needs because it rebuilds Suit-O's venv.
    """

    runner = popen or subprocess.Popen
    runner(
        ["cmd", "/c", "start", "Suit-O setup", str(script), "move"],
        cwd=str(Path(script).parent),
        **hidden_window_kwargs(),
    )
