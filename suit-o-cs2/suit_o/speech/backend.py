"""Swappable text-to-speech backend.

Implementations speak on a playback device only. They must not open a
microphone, write to a virtual cable, or touch Counter-Strike voice chat.
"""

from __future__ import annotations


class SpeechBackend:
    """Speak one line, possibly interrupted by ``stop``.

    ``speak`` runs on the speech thread and returns True if the line finished.
    ``stop`` may be called from another thread and must return quickly.
    """

    def speak(self, text: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError
