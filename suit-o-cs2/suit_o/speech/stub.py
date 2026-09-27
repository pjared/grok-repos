"""In-memory speech backend for tests and the simulator."""

from __future__ import annotations

import threading

from suit_o.speech.backend import SpeechBackend


class StubSpeechBackend(SpeechBackend):
    """Record lines instead of playing them. ``stop`` cancels the next speak."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.volume: float | None = None
        self.output_device: str | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    def speak(self, text: str) -> bool:
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        with self._lock:
            self.spoken.append(text)
        return True

    def set_volume(self, volume: float) -> None:
        self.volume = float(volume)

    def set_output_device(self, name: str) -> None:
        from suit_o.config import is_disallowed_output_device

        if is_disallowed_output_device(name):
            raise RuntimeError(
                f"Refusing playback device {name!r}. It looks like a microphone "
                "or a virtual cable into voice chat."
            )
        self.output_device = name

    def stop(self) -> None:
        self._cancel.set()

    def close(self) -> None:
        self.stop()
