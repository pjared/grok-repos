"""Render chat sentences with the cloned voice one step ahead of playback.

The chat model streams a reply sentence by sentence. Without this, the speech
thread synthesizes a sentence, plays it, and only then starts on the next one,
so every sentence boundary is a pause as long as the synthesis. Here a single
worker renders each sentence as soon as it arrives, in order, while the speech
thread plays the one before it.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger(__name__)

Render = Callable[[str], tuple[list[float], int]]


class ChatRenderer:
    """One worker, so sentences render in the order they were said."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pool: ThreadPoolExecutor | None = None
        self._pending: list[Future] = []

    def render(self, text: str, render: Render) -> Future:
        """Start rendering ``text`` with ``render``. The future holds (samples, rate)."""

        with self._lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="suit-o-chat-voice")
            self._pending = [future for future in self._pending if not future.done()]
            future = self._pool.submit(render, text)
            self._pending.append(future)
            return future

    def discard(self) -> int:
        """Cancel renders that have not started. Returns how many were dropped.

        A render already on the worker finishes, but nobody plays it.
        """

        with self._lock:
            pending, self._pending = self._pending, []
        return sum(1 for future in pending if future.cancel())

    def close(self) -> None:
        """Drop queued renders and stop the worker thread."""

        self.discard()
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
