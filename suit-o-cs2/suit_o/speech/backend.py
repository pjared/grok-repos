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

    def set_volume(self, volume: float) -> None:
        """Apply a volume in ``0.0`` … ``1.0``. Called on the speech thread."""

        return None

    def set_output_device(self, name: str) -> None:
        """Select a playback device. An empty name uses the Windows default.

        Called on the speech thread. Implementations must refuse a microphone
        or a virtual cable into voice chat.
        """

        return None
