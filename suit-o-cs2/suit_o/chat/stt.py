"""Local speech-to-text for chat push-to-talk.

The real model is imported only when a caller does not pass ``transcriber``.
Tests pass a fake and never download weights.
"""

from __future__ import annotations

import gc
from collections.abc import Callable

WHISPER_INSTALL = (
    "Push-to-talk needs faster-whisper. From the suit-o-cs2 folder run: "
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

    global _model
    from faster_whisper import WhisperModel

    if _model is None:
        device, compute = _stt_device()
        _model = WhisperModel("base", device=device, compute_type=compute)
    segments, _info = _model.transcribe(_pcm(samples), language="en")
    return " ".join(segment.text.strip() for segment in segments)


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
