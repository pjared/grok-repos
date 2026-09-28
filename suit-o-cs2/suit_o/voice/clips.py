"""Cut a long recording into training clips.

Silence boundaries use the audio-slicer algorithm. Resampling and peak
normalization use librosa when it is installed, which is how Chatterbox loads
a reference clip. No GUI here.
"""

from __future__ import annotations

import wave
from array import array
from pathlib import Path

from suit_o.voice.runtime import MODEL_SAMPLE_RATE
from suit_o.voice.wav import write_wav

_VOICE_INSTALL = (
    "Tick Voice training in Installations at the top of the window, or from the "
    "suit-o-cs2 folder run: python -m pip install -r requirements-voice.txt"
)

# Peak after normalize. Leaves a little headroom so 16-bit PCM does not clip.
TARGET_PEAK = 0.89


class ClipError(ValueError):
    """A clip could not be cut or saved."""


def split_on_silence(
    samples: list[float],
    sample_rate: int,
    *,
    threshold: float = -40,
    min_length: float = 0.4,
    min_silence: float = 0.3,
) -> list[tuple[float, float]]:
    """Speech regions as ``(start, end)`` seconds, from audio-slicer.

    ``threshold`` is a decibel level. A higher value (closer to 0) keeps only
    louder audio. A gap splits a region when the silence lasts at least
    ``min_silence`` seconds. Regions shorter than ``min_length`` are dropped.
    """

    if sample_rate < 1 or not samples:
        return []
    try:
        import numpy as np

        from suit_o.voice.audio_slicer import Slicer
    except ImportError as exc:
        raise ClipError(f"Auto-split needs numpy. {_VOICE_INSTALL}") from exc
    hop_ms = 10
    min_length_ms = max(hop_ms, int(round(float(min_length) * 1000)))
    min_interval_ms = max(hop_ms, int(round(float(min_silence) * 1000)))
    if min_interval_ms > min_length_ms:
        min_interval_ms = min_length_ms
    max_sil_kept = max(hop_ms, min(100, min_interval_ms))
    audio = np.asarray(samples, dtype=np.float32)
    try:
        slicer = Slicer(
            sr=int(sample_rate),
            threshold=float(threshold),
            min_length=min_length_ms,
            min_interval=min_interval_ms,
            hop_size=hop_ms,
            max_sil_kept=max_sil_kept,
        )
        spans = slicer.spans(audio)
    except (ValueError, OSError, RuntimeError) as exc:
        raise ClipError(f"Could not split that recording. {exc}") from exc
    regions: list[tuple[float, float]] = []
    minimum = max(0.0, float(min_length))
    for start, end in spans:
        begin = start / float(sample_rate)
        finish = end / float(sample_rate)
        if finish - begin + 1e-4 < minimum:
            continue
        regions.append((float(begin), float(finish)))
    return regions


def delete_regions(regions: list[tuple[float, float]], indexes: list[int]) -> list[tuple[float, float]]:
    chosen = set(indexes)
    return [region for index, region in enumerate(regions) if index not in chosen]


def merge_regions(regions: list[tuple[float, float]], indexes: list[int]) -> list[tuple[float, float]]:
    """Replace the chosen regions with one span from the earliest start to the latest end."""

    if len(indexes) < 2:
        return list(regions)
    chosen = sorted({index for index in indexes if 0 <= index < len(regions)})
    if len(chosen) < 2:
        return list(regions)
    picked = [regions[index] for index in chosen]
    span = (min(start for start, _end in picked), max(end for _start, end in picked))
    kept = [region for index, region in enumerate(regions) if index not in set(chosen)]
    kept.append(span)
    kept.sort(key=lambda region: (region[0], region[1]))
    return kept


def normalize_mono(samples: list[float], *, peak: float = TARGET_PEAK) -> list[float]:
    """Peak-normalize, then leave headroom at ``peak``.

    When librosa is installed this uses ``librosa.util.normalize``, the same
    library Chatterbox uses to load a reference. Silence stays silence.
    """

    if not samples:
        return []
    try:
        librosa, np = _librosa()
    except ClipError:
        loudest = max(abs(float(sample)) for sample in samples)
        if loudest < 1e-8:
            return [0.0] * len(samples)
        gain = float(peak) / loudest
        return [max(-1.0, min(1.0, float(sample) * gain)) for sample in samples]
    audio = np.asarray(samples, dtype=np.float32)
    loudest = float(np.max(np.abs(audio))) if audio.size else 0.0
    if loudest < 1e-8:
        return [0.0] * len(samples)
    normalized = librosa.util.normalize(audio, norm=np.inf)
    limited = np.clip(normalized * float(peak), -1.0, 1.0)
    return [float(sample) for sample in limited]


def _resample_for_model(samples: list[float], sample_rate: int, target_rate: int) -> list[float]:
    if sample_rate == target_rate:
        return list(samples)
    try:
        librosa, np = _librosa()
    except ClipError:
        from suit_o.voice.wav import resample

        new_length = max(1, int(round(len(samples) * target_rate / sample_rate)))
        return resample(samples, new_length)
    converted = librosa.resample(
        np.asarray(samples, dtype=np.float32),
        orig_sr=int(sample_rate),
        target_sr=int(target_rate),
    )
    return [float(sample) for sample in converted]


def slice_samples(samples: list[float], sample_rate: int, start: float, end: float) -> list[float]:
    if sample_rate < 1:
        raise ClipError("sample rate must be positive")
    begin = max(0, int(float(start) * sample_rate))
    finish = int(float(end) * sample_rate)
    finish = min(len(samples), max(begin + 1, finish))
    return list(samples[begin:finish])


def export_clip(
    samples: list[float],
    sample_rate: int,
    start: float,
    end: float,
    dest: Path,
    *,
    target_rate: int = MODEL_SAMPLE_RATE,
) -> tuple[list[float], int]:
    """Write one normalized mono WAV at the voice model's sample rate."""

    if end <= start:
        raise ClipError("The clip's out point has to be after the in point")
    piece = slice_samples(samples, sample_rate, start, end)
    if not piece:
        raise ClipError("That clip is empty")
    piece = _resample_for_model(piece, sample_rate, target_rate)
    piece = normalize_mono(piece)
    write_wav(dest, piece, target_rate)
    return piece, target_rate


def seek_time(position: float, delta: float, duration: float) -> float:
    return min(max(0.0, duration), max(0.0, position + delta))


def move_in(in_point: float, out_point: float, delta: float, *, gap: float = 0.05) -> float:
    return min(max(0.0, in_point + delta), max(0.0, out_point - gap))


def move_out(in_point: float, out_point: float, delta: float, duration: float, *, gap: float = 0.05) -> float:
    return max(min(max(0.0, duration), out_point + delta), min(duration, in_point + gap))


def zoom_window(
    view_start: float,
    view_span: float,
    duration: float,
    anchor: float,
    factor: float,
) -> tuple[float, float]:
    """Zoom around ``anchor``. A factor below 1 zooms in."""

    if duration <= 0:
        return 0.0, 0.0
    span = min(duration, max(0.5, view_span * factor))
    if span >= duration - 1e-6:
        return 0.0, duration
    start = min(max(0.0, anchor - span / 2), duration - span)
    return start, span


def load_media(path: Path) -> tuple[list[float], int]:
    """Load a WAV directly, or extract audio from another format with ffmpeg."""

    source = Path(path)
    if not source.is_file():
        raise ClipError(f"File not found: {source}")
    if source.suffix.lower() == ".wav":
        try:
            return read_wav_mono(source)
        except (ClipError, OSError, wave.Error):
            pass
    from tempfile import TemporaryDirectory

    from suit_o.voice.ffmpeg import extract_audio

    with TemporaryDirectory() as folder:
        dest = Path(folder) / "extracted.wav"
        extract_audio(source, dest, sample_rate=MODEL_SAMPLE_RATE)
        return read_wav_mono(dest)


def _librosa():
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise ClipError(f"Saving a clip needs librosa. {_VOICE_INSTALL}") from exc
    return librosa, np


def read_wav_mono(path: Path) -> tuple[list[float], int]:
    """Read 16-bit PCM and downmix every channel to mono."""

    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2 or channels < 1 or rate < 1:
        raise ClipError(f"{path.name} is not 16-bit PCM")
    pcm = array("h")
    pcm.frombytes(frames)
    if channels == 1:
        return [sample / 32767.0 for sample in pcm], rate
    mixed: list[float] = []
    for index in range(0, len(pcm) - channels + 1, channels):
        frame = pcm[index : index + channels]
        mixed.append(sum(frame) / (len(frame) * 32767.0))
    return mixed, rate
