"""Reserved remote TTS backend. Not implemented in v1.

A later version may send text to an HTTP TTS server on a home-LAN machine
(the intended host is a DGX Spark) and play the returned audio. That client
must not be added until the playback path is still a local output device and
still cannot reach voice chat. This module deliberately has no HTTP code.
"""

from __future__ import annotations

from suit_o.config import SpeechConfig
from suit_o.speech.backend import SpeechBackend


class RemoteTtsBackend(SpeechBackend):
    """Placeholder selected by ``speech.backend: remote``.

    Construction fails on purpose. A half-configured install must not silently
    fall back to another engine or open a socket.
    """

    def __init__(self, settings: SpeechConfig) -> None:
        del settings
        raise NotImplementedError(
            "The remote TTS backend is not implemented in Suit-O v1. "
            "Set speech.backend to pyttsx3. A future version may POST text to "
            "speech.remote.url (an HTTP TTS server on the home LAN, such as a "
            "DGX Spark) and play the returned audio on the configured playback "
            "device only. It must not route audio into Counter-Strike voice chat."
        )

    def speak(self, text: str) -> bool:
        del text
        raise NotImplementedError

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None
