"""Load the plain-text voice script."""

from __future__ import annotations

from pathlib import Path

from suit_o.config import PROJECT_ROOT

DEFAULT_SCRIPT_PATH = PROJECT_ROOT / "voice_script.txt"


class ScriptError(ValueError):
    """The voice script file is missing or empty."""


def load_script(path: Path | None = None) -> list[str]:
    """Return spoken lines. Blank lines and ``#`` comments are skipped."""

    script_path = Path(path) if path is not None else DEFAULT_SCRIPT_PATH
    if not script_path.is_file():
        raise ScriptError(f"Voice script not found: {script_path}")
    lines: list[str] = []
    for raw in script_path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        lines.append(text)
    if not lines:
        raise ScriptError(f"Voice script {script_path} has no spoken lines")
    return lines
