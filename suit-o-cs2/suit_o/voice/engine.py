"""Chatterbox synthesis. Imported only while pre-rendering or previewing a line."""

from __future__ import annotations

import threading
from pathlib import Path

from suit_o.voice.runtime import INSTALL_HINT, synthesis_device

_LOCK = threading.Lock()
_MODEL = None
_MODEL_DEVICE = ""

# Chatterbox exaggeration. Strong is the jittery end of the same control.
_EXAGGERATION = {"none": 0.5, "mild": 0.7, "strong": 0.95}


def exaggeration_for(emphasis: str) -> float:
    return _EXAGGERATION.get(emphasis, 0.5)


def release_model() -> None:
    """Drop the loaded model so a match does not keep the GPU resident.

    Safe to call when the optional stack was never imported. Does not download
    weights.
    """

    global _MODEL, _MODEL_DEVICE
    with _LOCK:
        model = _MODEL
        _MODEL = None
        _MODEL_DEVICE = ""
    del model
    try:
        import torch
    except ImportError:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return


def synthesize(text: str, prompt_wav: Path, emphasis: str = "none") -> tuple[list[float], int]:
    """Clone ``prompt_wav`` and speak ``text``. Returns float samples and the rate.

    The model is loaded on the first call. CUDA is used when
    ``torch.cuda.is_available()``; otherwise the same call runs on CPU.
    Call :func:`release_model` after a render batch or a preview so a match
    does not keep using the GPU.
    """

    cleaned = text.strip()
    if not cleaned:
        raise RuntimeError("Nothing to speak")
    if not prompt_wav.is_file():
        raise RuntimeError(f"Cloned voice is missing its prompt audio: {prompt_wav}")
    device = synthesis_device()
    with _LOCK:
        model = _load_model(device)
        try:
            wav = model.generate(
                cleaned,
                audio_prompt_path=str(prompt_wav),
                exaggeration=exaggeration_for(emphasis),
            )
        except TypeError:
            wav = model.generate(cleaned, audio_prompt_path=str(prompt_wav))
    return _to_samples(wav), int(getattr(model, "sr", 24000))


def _load_model(device: str):
    global _MODEL, _MODEL_DEVICE
    if _MODEL is not None and _MODEL_DEVICE == device:
        return _MODEL
    try:
        from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:
        raise RuntimeError(INSTALL_HINT) from exc
    _MODEL = ChatterboxTTS.from_pretrained(device=device)
    _MODEL_DEVICE = device
    return _MODEL


def _to_samples(wav: object) -> list[float]:
    if hasattr(wav, "detach"):
        wav = wav.detach().cpu().float().reshape(-1).tolist()  # type: ignore[union-attr]
        return [float(sample) for sample in wav]
    if hasattr(wav, "reshape"):
        flat = wav.reshape(-1).tolist()  # type: ignore[union-attr]
        return [float(sample) for sample in flat]
    return [float(sample) for sample in wav]  # type: ignore[arg-type]
