"""Local speech-to-text for chat push-to-talk.

The real model is imported only when a caller does not pass ``transcriber``.
Tests pass a fake and never download weights.
"""

from __future__ import annotations

import gc
from collections.abc import Callable

WHISPER_INSTALL = (
    "Push-to-talk needs faster-whisper. Tick Push-to-talk in Installations at the top "
    "of the window, or from the suit-o-cs2 folder run: "
    "python -m pip install -r requirements-chat.txt"
)


class SttError(RuntimeError):
    """Speech-to-text is missing or could not hear the clip."""


_model = None


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def transcribe(
    samples: list[float],
    sample_rate: int,
    *,
    transcriber: Callable[[list[float], int], str] | None = None,
) -> str:
    """Turn one microphone clip into text. ``transcriber`` skips the real model."""

    if transcriber is not None:
        text = transcriber(samples, sample_rate)
        return str(text or "").strip()
    if not whisper_available():
        raise SttError(WHISPER_INSTALL)
    if sample_rate < 1 or not samples:
        raise SttError("That clip had no audio")
    return _faster_whisper(samples, sample_rate).strip()


def preload_stt() -> bool:
    """Load the speech model now, while the user is still holding the key.

    Returns False when faster-whisper is not installed or the model cannot load.
    """

    if not whisper_available():
        return False
    try:
        _whisper_model()
    except Exception:
        return False
    return True


def release_stt() -> None:
    """Drop the cached speech model so it is not sitting in VRAM."""

    global _model
    _model = None
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    empty = getattr(getattr(torch, "cuda", None), "empty_cache", None)
    if empty is not None:
        try:
            empty()
        except Exception:
            return


def _faster_whisper(samples: list[float], sample_rate: int) -> str:
    """Run faster-whisper. Not used by tests."""

    model = _whisper_model()
    # One beam and no carried-over context: a push-to-talk clip is a single
    # short phrase, and beam search mostly adds delay.
    segments, _info = model.transcribe(
        _pcm(samples),
        language="en",
        beam_size=1,
        condition_on_previous_text=False,
    )
    return " ".join(segment.text.strip() for segment in segments)


def _whisper_model():
    global _model
    from faster_whisper import WhisperModel

    if _model is None:
        device, compute = _stt_device()
        _model = WhisperModel("base", device=device, compute_type=compute)
    return _model


def _stt_device() -> tuple[str, str]:
    try:
        import ctranslate2

        if int(ctranslate2.get_cuda_device_count()) > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _pcm(samples: list[float]):
    try:
        import numpy as np
    except ImportError as exc:
        raise SttError(WHISPER_INSTALL) from exc
    audio = np.asarray(samples, dtype=np.float32)
    return audio
