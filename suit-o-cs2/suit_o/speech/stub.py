"""In-memory speech backend for tests and the simulator."""

from __future__ import annotations

import threading

from suit_o.speech.backend import SpeechBackend


class StubSpeechBackend(SpeechBackend):
    """Record lines instead of playing them. ``stop`` cancels the next speak."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    def speak(self, text: str) -> bool:
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        with self._lock:
            self.spoken.append(text)
        return True

    def stop(self) -> None:
        self._cancel.set()

    def close(self) -> None:
        self.stop()
