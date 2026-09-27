"""Optional cleanup before a clip is cut.

Vocal separation uses Demucs. Speaker tags use pyannote.audio. Both are
optional. Manual in/out points and the silence slicer do not import them.
Tests pass a callable so nothing downloads a model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from suit_o.voice.clips import ClipError

CLIPS_INSTALL = (
    "From the suit-o-cs2 folder run: python -m pip install -r requirements-clips.txt"
)
DEMUCS_INSTALL = f"Vocal separation needs Demucs. {CLIPS_INSTALL}"
PYANNOTE_INSTALL = f"Speaker tags need pyannote.audio. {CLIPS_INSTALL}"
HF_SETUP = (
    "Speaker tags need a Hugging Face token. Create one, accept the terms for "
    "pyannote/speaker-diarization-3.1, then set HUGGING_FACE_HUB_TOKEN "
    "(or HF_TOKEN), or add huggingface_token to config.local.yaml. "
    "That file is gitignored. Suit-O does not print the token."
)


@dataclass(frozen=True)
class SpeakerTurn:
    speaker: str
    start: float
    end: float


def demucs_available() -> bool:
    try:
        import demucs.apply  # noqa: F401
    except Exception:
        return False
    return True


def pyannote_available() -> bool:
    try:
        import pyannote.audio  # noqa: F401
    except Exception:
        return False
    return True


def demucs_status() -> tuple[bool, str]:
    if demucs_available():
        return True, ""
    return False, DEMUCS_INSTALL


def pyannote_status() -> tuple[bool, str]:
    if pyannote_available():
        return True, ""
    return False, PYANNOTE_INSTALL


def read_hf_token(config_path: Path | None = None) -> str:
    """Token from the environment or config.local.yaml. Never logged here."""

    for name in ("HUGGING_FACE_HUB_TOKEN", "HF_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if config_path is None:
        return ""
    from suit_o.config import ConfigError, read_yaml_mapping
    from suit_o.local_config import local_config_path

    path = local_config_path(Path(config_path))
    if not path.is_file():
        return ""
    try:
        raw = read_yaml_mapping(path, empty_ok=True)
    except (ConfigError, OSError):
        return ""
    value = raw.get("huggingface_token")
    if not isinstance(value, str):
        return ""
    return value.strip()


def separate_vocals(samples: list[float], sample_rate: int, *, separator=None) -> list[float]:
    """Return the vocal stem. ``separator`` is the test double."""

    if separator is not None:
        return [float(sample) for sample in separator(samples, sample_rate)]
    if not demucs_available():
        raise ClipError(DEMUCS_INSTALL)
    return _separate_with_demucs(samples, sample_rate)


def diarize(samples: list[float], sample_rate: int, *, token: str, diarizer=None) -> list[SpeakerTurn]:
    """Tag speakers. ``diarizer`` is the test double. The token is not logged."""

    if not pyannote_available() and diarizer is None:
        raise ClipError(PYANNOTE_INSTALL)
    cleaned = token.strip()
    if not cleaned:
        raise ClipError(HF_SETUP)
    try:
        if diarizer is not None:
            found = diarizer(samples, sample_rate)
        else:
            found = _diarize_with_pyannote(samples, sample_rate, cleaned)
    except ClipError:
        raise
    except Exception as exc:
        raise ClipError(_redact(f"Could not tag speakers. {exc}", cleaned)) from exc
    turns: list[SpeakerTurn] = []
    for turn in found:
        turns.append(SpeakerTurn(str(turn.speaker), float(turn.start), float(turn.end)))
    return turns


def isolate_speaker(
    samples: list[float],
    sample_rate: int,
    turns: list[SpeakerTurn],
    speaker: str,
) -> list[float]:
    """Keep one speaker's samples and silence the rest. The timeline stays put."""

    if sample_rate < 1:
        raise ClipError("sample rate must be positive")
    isolated = [0.0] * len(samples)
    for turn in turns:
        if turn.speaker != speaker:
            continue
        start = max(0, int(turn.start * sample_rate))
        end = min(len(samples), int(turn.end * sample_rate))
        if end > start:
            isolated[start:end] = samples[start:end]
    return isolated


def _redact(message: str, token: str) -> str:
    if token and token in message:
        return message.replace(token, "[token]")
    return message


def _separate_with_demucs(samples: list[float], sample_rate: int) -> list[float]:
    import numpy as np
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model("htdemucs")
    model.eval()
    audio = np.asarray(samples, dtype=np.float32)
    wav = torch.from_numpy(audio).float().unsqueeze(0).unsqueeze(0)
    target = int(getattr(model, "samplerate", sample_rate))
    if sample_rate != target:
        wav = _resample_tensor(wav, sample_rate, target)
    from suit_o.voice.runtime import torch_inference_device

    with torch.no_grad():
        sources = apply_model(model, wav, device=torch_inference_device(torch))
    names = list(getattr(model, "sources", []))
    index = names.index("vocals") if "vocals" in names else 0
    vocals = sources[0, index].mean(dim=0)
    if target != sample_rate:
        vocals = _resample_tensor(vocals.unsqueeze(0).unsqueeze(0), target, sample_rate)[0, 0]
    return [float(sample) for sample in vocals.detach().cpu()]


def _diarize_with_pyannote(samples: list[float], sample_rate: int, token: str) -> list[SpeakerTurn]:
    import numpy as np
    import torch
    from pyannote.audio import Pipeline

    try:
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
    waveform = torch.from_numpy(np.asarray(samples, dtype=np.float32)).unsqueeze(0)
    output = pipeline({"waveform": waveform, "sample_rate": int(sample_rate)})
    turns: list[SpeakerTurn] = []
    for turn, _track, speaker in output.itertracks(yield_label=True):
        turns.append(SpeakerTurn(str(speaker), float(turn.start), float(turn.end)))
    return turns


def _resample_tensor(wav, source_rate: int, target_rate: int):
    import torch

    if source_rate == target_rate:
        return wav
    squeezed = wav
    while squeezed.dim() > 1 and squeezed.shape[0] == 1:
        squeezed = squeezed.squeeze(0)
    new_length = max(1, int(round(squeezed.shape[-1] * target_rate / source_rate)))
    resized = torch.nn.functional.interpolate(
        squeezed.unsqueeze(0).unsqueeze(0),
        size=new_length,
        mode="linear",
        align_corners=False,
    )
    return resized
