"""Whether the optional cloning stack is installed, and which device it would use."""

from __future__ import annotations

from dataclasses import dataclass

INSTALL_HINT = (
    "Optional voice cloning is not installed. Tick Voice training in Installations at "
    "the top of the window, or from the suit-o-cs2 folder run: "
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
    """Return cuda, rocm, cpu, or unavailable. Does not download model weights.

    The summary names the stack in use. It does not name the graphics card.
    """

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
    device, summary = describe_accelerator(*_torch_flags(torch), directml=_directml_ready())
    return RuntimeStatus(True, device, summary)


def describe_accelerator(cuda: bool, hip: bool, *, directml: bool) -> tuple[str, str]:
    """Pick CUDA, ROCm, or CPU for Chatterbox.

    ROCm uses PyTorch's CUDA API, so synthesis still asks for ``cuda``.
    DirectML is reported when that library is installed, and Chatterbox stays
    on the CPU because this model does not run on it. No graphics-card name
    is included.
    """

    if cuda and hip:
        return (
            "rocm",
            "Chatterbox on AMD ROCm. Matches play the saved files.",
        )
    if cuda:
        return (
            "cuda",
            "Chatterbox on NVIDIA CUDA. Matches play the saved files.",
        )
    if directml:
        return (
            "cpu",
            "Chatterbox on CPU. DirectML is installed, and this voice model does not use it. "
            "Matches play the saved files.",
        )
    return (
        "cpu",
        "Chatterbox on CPU. No CUDA, ROCm, or DirectML device was found, so building speech is slower. "
        "Matches play the saved files.",
    )


def synthesis_device() -> str:
    """``cuda`` or ``cpu``. ROCm is ``cuda`` because that build uses the CUDA API.

    Raises if the optional stack is missing.
    """

    status = runtime_status()
    if not status.installed:
        raise RuntimeError(status.summary)
    if status.device in {"cuda", "rocm"}:
        return "cuda"
    return "cpu"


def torch_inference_device(torch_module) -> str:
    """``cuda`` when this torch build is NVIDIA CUDA or AMD ROCm, else ``cpu``.

    Callers that only accept those two strings use this. DirectML is not one
    of them. ROCm reports itself through ``cuda.is_available()``.
    """

    cuda, _hip = _torch_flags(torch_module)
    return "cuda" if cuda else "cpu"


def _torch_flags(torch_module) -> tuple[bool, bool]:
    cuda = False
    try:
        cuda = bool(torch_module.cuda.is_available())
    except Exception:
        cuda = False
    version = getattr(torch_module, "version", None)
    hip = bool(getattr(version, "hip", None))
    return cuda, hip


def _directml_ready() -> bool:
    try:
        import torch_directml
    except Exception:
        return False
    try:
        return torch_directml.device() is not None
    except Exception:
        return False
