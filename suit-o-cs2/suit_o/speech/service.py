"""Background speech queue with priority preemption.

Small lines wait their turn. A big moment (priority at or above the configured
floor, and higher than whatever is currently playing) interrupts it. Audio
never goes anywhere except the active backend.
"""

from __future__ import annotations

import logging
import threading

from suit_o.models import Utterance
from suit_o.speech.backend import SpeechBackend

logger = logging.getLogger(__name__)

_MAX_PENDING = 8


class SpeechService:
    def __init__(self, backend: SpeechBackend, preempt_min_priority: int) -> None:
        self.backend = backend
        self.preempt_min_priority = preempt_min_priority
        self.history: list[Utterance] = []
        self._pending: list[Utterance] = []
        self._current: Utterance | None = None
        self._muted = False
        self._stop = False
        self._cv = threading.Condition()
        self._thread = threading.Thread(target=self._loop, name="suit-o-speech", daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def submit(self, utterance: Utterance) -> None:
        with self._cv:
            if self._muted or self._stop:
                return
            self._pending.append(utterance)
            self._pending.sort(key=lambda item: -item.priority)
            if len(self._pending) > _MAX_PENDING:
                dropped = self._pending[_MAX_PENDING :]
                del self._pending[_MAX_PENDING :]
                logger.warning("Dropped %s queued line(s) above the speech cap", len(dropped))
            if (
                self._current is not None
                and utterance.priority > self._current.priority
                and utterance.priority >= self.preempt_min_priority
            ):
                self.backend.stop()
            self._cv.notify()

    def set_muted(self, muted: bool) -> None:
        with self._cv:
            self._muted = muted
            if muted:
                self._pending.clear()
                if self._current is not None:
                    self.backend.stop()
            self._cv.notify_all()

    def wait_until(self, ready, timeout: float) -> bool:
        """Block until ``ready()`` is true and the queue is idle, or time out.

        Polls briefly so a caller can wait on work that happens outside this
        condition variable (the GSI worker's processed count, for example).
        """

        deadline = _now() + timeout
        while True:
            with self._cv:
                idle = not self._pending and self._current is None
            if ready() and idle:
                return True
            remaining = deadline - _now()
            if remaining <= 0:
                return False
            with self._cv:
                self._cv.wait(min(remaining, 0.05))

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._pending.clear()
            self._cv.notify_all()
        self.backend.stop()
        if self._started:
            self._thread.join(timeout=2)
        self.backend.close()

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._pending and not self._stop:
                    self._cv.wait()
                if self._stop and not self._pending:
                    return
                utterance = self._pending.pop(0)
                if self._muted:
                    continue
                self._current = utterance
            completed = False
            try:
                completed = bool(self.backend.speak(utterance.text))
            except Exception:
                logger.exception("Speech backend failed")
            with self._cv:
                if completed and not self._muted:
                    self.history.append(utterance)
                self._current = None
                self._cv.notify_all()


def _now() -> float:
    import time

    return time.monotonic()
