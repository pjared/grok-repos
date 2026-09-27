"""Speech output. Backends are selected from config, not by editing callers."""

from suit_o.speech.backend import SpeechBackend
from suit_o.speech.factory import create_backend
from suit_o.speech.service import SpeechService

__all__ = ["SpeechBackend", "SpeechService", "create_backend"]
