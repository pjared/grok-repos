"""When the Chat tab may talk.

A live round is the only block. The menu, warmup, and the gap between
matches stay open so chat does not sit on top of in-game lines.
"""

from __future__ import annotations


def chat_is_paused(
    activity: str | None,
    round_phase: str | None,
    map_phase: str | None = None,
) -> bool:
    """True while GSI says the round phase is live, outside menu and warmup."""

    if (round_phase or "").strip().lower() != "live":
        return False
    if (map_phase or "").strip().lower() == "warmup":
        return False
    if (activity or "").strip().lower() == "menu":
        return False
    return True
