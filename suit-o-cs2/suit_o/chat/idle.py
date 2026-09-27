"""Drop resident chat models after the tab goes quiet.

A live round releases them immediately so the GPU is not holding VRAM
for a conversation that cannot run.
"""

from __future__ import annotations

from collections.abc import Callable

IDLE_RELEASE_SECONDS = 60.0


class IdleRelease:
    """Call ``release`` once the chat has been unused, or a round goes live.

    ``touch`` marks a model as resident. Nothing is released until then, so
    an unused tab does not poke a server.
    """

    def __init__(self, release: Callable[[], None], *, wait: float = IDLE_RELEASE_SECONDS) -> None:
        self._release = release
        self.wait = wait
        self._touched: float | None = None
        self._resident = False

    @property
    def resident(self) -> bool:
        return self._resident

    def touch(self, now: float) -> None:
        self._touched = now
        self._resident = True

    def poll(self, now: float, *, busy: bool, paused: bool) -> bool:
        if not self._resident:
            return False
        if busy:
            self._touched = now
            return False
        idle = self._touched is not None and now - self._touched >= self.wait
        if not paused and not idle:
            return False
        self._resident = False
        self._release()
        return True
