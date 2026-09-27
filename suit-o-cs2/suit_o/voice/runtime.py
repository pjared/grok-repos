"""Whether the optional cloning stack is installed, and which device it would use."""

from __future__ import annotations

from dataclasses import dataclass

INSTALL_HINT = (
    "Optional voice cloning is not installed. From the suit-o-cs2 folder run: "
    "python -m pip install -r requirements-voice.txt"
)

MODEL_ID = "chatterbox"
MODEL_NAME = "Chatterbox"
# Chatterbox's default rate. Training clips are saved at this rate.
MODEL_SAMPLE_RATE = 24000


@dataclass(frozen=True)
class RuntimeStatus:
    """What the Voice Training tab should say about the local cloner."""

    installed: bool
    device: str
    summary: str


def runtime_status() -> RuntimeStatus:
    """Return cuda, cpu, or unavailable. Does not download model weights."""

    try:
        import torch
    except Exception:
        return RuntimeStatus(False, "unavailable", INSTALL_HINT)
    try:
        import chatterbox.tts  # noqa: F401
    except Exception:
        return RuntimeStatus(False, "unavailable", INSTALL_HINT)
    try:
        import sounddevice  # noqa: F401
    except Exception:
        return RuntimeStatus(False, "unavailable", INSTALL_HINT)
    if bool(torch.cuda.is_available()):
        try:
            gpu_name = str(torch.cuda.get_device_name(0))
        except Exception:
            gpu_name = "NVIDIA GPU"
        return RuntimeStatus(True, "cuda", f"Chatterbox on NVIDIA CUDA ({gpu_name})")
    return RuntimeStatus(
        True,
        "cpu",
        "Chatterbox on CPU. No NVIDIA CUDA device was found, so building speech is slower.",
    )


def synthesis_device() -> str:
    """``cuda`` or ``cpu``. Raises if the optional stack is missing."""

    status = runtime_status()
    if not status.installed:
        raise RuntimeError(status.summary)
    return "cuda" if status.device == "cuda" else "cpu"
