"""Corner placement for the overlay. Pure arithmetic, no window toolkit."""

from __future__ import annotations

from dataclasses import dataclass

CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")
MARGIN = 16


@dataclass(frozen=True)
class Monitor:
    """One display, in virtual-screen pixels."""

    index: int
    x: int
    y: int
    width: int
    height: int
    label: str


def place_overlay(
    monitor: Monitor,
    corner: str,
    width: int,
    height: int,
    *,
    margin: int = MARGIN,
) -> tuple[int, int]:
    """Top-left of the overlay window for ``corner`` on ``monitor``."""

    name = corner.strip().lower()
    if name not in CORNERS:
        name = "top-right"
    if name.endswith("right"):
        x = monitor.x + monitor.width - width - margin
    else:
        x = monitor.x + margin
    if name.startswith("bottom"):
        y = monitor.y + monitor.height - height - margin
    else:
        y = monitor.y + margin
    return x, y


def pick_monitor(monitors: list[Monitor], index: int) -> Monitor:
    """Return the requested display, or the first one when the index is stale."""

    if not monitors:
        return Monitor(0, 0, 0, 1920, 1080, "Primary")
    for monitor in monitors:
        if monitor.index == index:
            return monitor
    return monitors[0]
