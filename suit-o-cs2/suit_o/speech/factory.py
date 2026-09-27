"""Build the speech backend named in config."""

from __future__ import annotations

from suit_o.config import ConfigError, SpeechConfig
from suit_o.speech.backend import SpeechBackend


def create_backend(settings: SpeechConfig) -> SpeechBackend:
    kind = settings.backend
    if kind == "stub":
        from suit_o.speech.stub import StubSpeechBackend

        return StubSpeechBackend()
    if kind == "pyttsx3":
        from suit_o.speech.pyttsx3_backend import Pyttsx3Backend

        return Pyttsx3Backend(settings)
    if kind == "remote":
        from suit_o.speech.remote import RemoteTtsBackend

        return RemoteTtsBackend(settings)
    raise ConfigError(f"Unknown speech backend {kind!r}")
