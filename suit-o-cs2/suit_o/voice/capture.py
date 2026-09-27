"""Microphone capture and speaker playback.

Used by the Voice Training tab and the cloned-voice backend. A missing
``sounddevice`` install raises :data:`INSTALL_HINT` instead of importing it
at startup. Playback still refuses a microphone or virtual-cable name.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from suit_o.config import is_disallowed_output_device
from suit_o.voice.runtime import INSTALL_HINT
from suit_o.voice.wav import apply_volume, read_wav, write_wav

_SAMPLE_RATE = 24000


class CaptureError(RuntimeError):
    """The audio device could not be opened."""


def list_input_device_names() -> list[str]:
    """Recording devices. Microphones are allowed here; this is not playback."""

    sd = _sounddevice()
    names: list[str] = []
    for entry in sd.query_devices():
        try:
            channels = int(entry["max_input_channels"])
            name = str(entry["name"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if channels > 0 and name and name not in names:
            names.append(name)
    return names


def record_wav(device_name: str, cancel: threading.Event, level: list[float]) -> bytes:
    """Record mono audio until ``cancel`` is set. ``level[0]`` tracks RMS."""

    sd = _sounddevice()
    import numpy as np

    device = _input_index(sd, device_name)
    chunks: list = []

    def callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
        if status:
            pass
        copy = indata.copy()
        chunks.append(copy)
        flat = copy.reshape(-1)
        if flat.size:
            level[0] = float(np.sqrt(np.mean(np.square(flat))))
        else:
            level[0] = 0.0

    try:
        stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=device,
            callback=callback,
        )
    except Exception as exc:
        raise CaptureError(f"Could not open microphone {device_name!r}. {exc}") from exc
    with stream:
        while not cancel.is_set():
            time.sleep(0.05)
    level[0] = 0.0
    if not chunks:
        return b""
    joined = np.concatenate(chunks, axis=0).reshape(-1)
    samples = [float(sample) for sample in joined]
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        path = Path(folder) / "take.wav"
        write_wav(path, samples, _SAMPLE_RATE)
        return path.read_bytes()


def play_wav_file(path: Path, output_device: str, *, volume: float = 1.0, cancel: threading.Event | None = None) -> bool:
    """Play a WAV on a playback device. Returns False when ``cancel`` fires."""

    if is_disallowed_output_device(output_device):
        raise CaptureError(
            f"Refusing playback device {output_device!r}. It looks like a microphone "
            "or a virtual cable into voice chat."
        )
    samples, rate = read_wav(path)
    return play_samples(samples, rate, output_device, volume=volume, cancel=cancel)


def play_samples(
    samples: list[float],
    sample_rate: int,
    output_device: str,
    *,
    volume: float = 1.0,
    cancel: threading.Event | None = None,
) -> bool:
    if is_disallowed_output_device(output_device):
        raise CaptureError(
            f"Refusing playback device {output_device!r}. It looks like a microphone "
            "or a virtual cable into voice chat."
        )
    sd = _sounddevice()
    import numpy as np

    scaled = apply_volume(samples, volume)
    audio = np.asarray(scaled, dtype="float32")
    device = None if not output_device.strip() else _output_index(sd, output_device)
    try:
        sd.play(audio, sample_rate, device=device)
    except Exception as exc:
        raise CaptureError(f"Could not play on {output_device or 'the default device'!r}. {exc}") from exc
    while True:
        stream = sd.get_stream()
        active = bool(getattr(stream, "active", False))
        if not active:
            break
        if cancel is not None and cancel.is_set():
            sd.stop()
            return False
        time.sleep(0.05)
    if cancel is not None and cancel.is_set():
        sd.stop()
        return False
    return True


def _sounddevice():
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise CaptureError(INSTALL_HINT) from exc
    return sd


def _input_index(sd: object, name: str) -> int:
    return _match_index(sd, name, want_input=True)


def _output_index(sd: object, name: str) -> int:
    return _match_index(sd, name, want_input=False)


def _match_index(sd: object, name: str, *, want_input: bool) -> int:
    needle = name.strip().lower()
    devices = sd.query_devices()  # type: ignore[attr-defined]
    exact: int | None = None
    partial: int | None = None
    for index, entry in enumerate(devices):
        channels = int(entry["max_input_channels"] if want_input else entry["max_output_channels"])
        if channels < 1:
            continue
        label = str(entry["name"]).strip()
        if label.lower() == needle:
            exact = index
            break
        if needle and needle in label.lower() and partial is None:
            partial = index
    chosen = exact if exact is not None else partial
    if chosen is None:
        kind = "microphone" if want_input else "playback device"
        raise CaptureError(f"No {kind} matches {name!r}")
    return chosen
