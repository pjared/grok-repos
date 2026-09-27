"""Suit-O's chat persona. The text file reloads the next time someone talks."""

from __future__ import annotations

from pathlib import Path

from suit_o.config import PROJECT_ROOT

PERSONA_PATH = PROJECT_ROOT / "lines" / "persona.txt"

_FALLBACK = (
    "You are Suit-O, an eager, jittery, over-apologetic helper and teammate. "
    "Keep replies to one or two short sentences. "
    "Do not reproduce copyrighted game dialogue."
)


def load_persona(path: Path | None = None) -> str:
    """Read the persona file. A missing or empty file uses a short fallback."""

    source = Path(path) if path is not None else PERSONA_PATH
    try:
        text = source.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK
    return text or _FALLBACK
