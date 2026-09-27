"""In-memory speech backend for tests and the simulator."""

from __future__ import annotations

import threading

from suit_o.speech.backend import SpeechBackend
from suit_o.speech.tuning import VoiceTuning, normalize_tuning


class StubSpeechBackend(SpeechBackend):
    """Record lines instead of playing them. ``stop`` cancels the next speak."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.spoken_tuning: list[VoiceTuning | None] = []
        self.tuning: VoiceTuning | None = None
        self.volume: float | None = None
        self.output_device: str | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    def speak(self, text: str, tuning: VoiceTuning | None = None) -> bool:
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        used = self.tuning if tuning is None else normalize_tuning(tuning)
        with self._lock:
            self.spoken.append(text)
            self.spoken_tuning.append(used)
        return True

    def apply_tuning(self, tuning: object) -> None:
        applied = normalize_tuning(tuning)  # type: ignore[arg-type]
        self.tuning = applied
        self.volume = applied.volume

    def set_volume(self, volume: float) -> None:
        self.volume = float(volume)
        if self.tuning is not None:
            self.tuning = VoiceTuning(
                voice=self.tuning.voice,
                rate=self.tuning.rate,
                volume=float(volume),
                pitch=self.tuning.pitch,
                pause_ms=self.tuning.pause_ms,
                emphasis=self.tuning.emphasis,
            )

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
