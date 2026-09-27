"""Cut a long recording into training clips. No GUI and no ffmpeg."""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path

from suit_o.voice.runtime import MODEL_SAMPLE_RATE
from suit_o.voice.wav import resample, write_wav

# Peak after normalize. Leaves a little headroom so 16-bit PCM does not clip.
TARGET_PEAK = 0.89


class ClipError(ValueError):
    """A clip could not be cut or saved."""


def split_on_silence(
    samples: list[float],
    sample_rate: int,
    *,
    threshold: float = 0.02,
    min_length: float = 0.4,
    min_silence: float = 0.3,
) -> list[tuple[float, float]]:
    """Speech regions as ``(start, end)`` seconds.

    A gap counts as a split only when the silence lasts at least
    ``min_silence`` seconds. Regions shorter than ``min_length`` are dropped.
    ``threshold`` is an RMS level from 0 to 1.
    """

    if sample_rate < 1 or not samples:
        return []
    level = max(0.0, float(threshold))
    window = max(1, int(sample_rate * 0.02))
    flags: list[bool] = []
    for start in range(0, len(samples), window):
        chunk = samples[start : start + window]
        if not chunk:
            break
        energy = sum(sample * sample for sample in chunk) / len(chunk)
        flags.append(math.sqrt(energy) < level)
    if not flags:
        return []
    gap_windows = max(1, int(math.ceil(max(0.0, min_silence) * sample_rate / window)))
    regions: list[tuple[int, int]] = []
    speech_start: int | None = None
    silent_run = 0
    for index, silent in enumerate(flags):
        if silent:
            silent_run += 1
            if speech_start is not None and silent_run >= gap_windows:
                regions.append((speech_start, index - silent_run + 1))
                speech_start = None
        else:
            silent_run = 0
            if speech_start is None:
                speech_start = index
    if speech_start is not None:
        regions.append((speech_start, len(flags)))
    seconds: list[tuple[float, float]] = []
    minimum = max(0.0, float(min_length))
    for start, end in regions:
        begin = start * window / sample_rate
        finish = min(len(samples), end * window) / sample_rate
        if finish - begin >= minimum:
            seconds.append((begin, finish))
    return seconds


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
    """Scale the loudest sample to ``peak``. Silence stays silence."""

    if not samples:
        return []
    loudest = max(abs(float(sample)) for sample in samples)
    if loudest < 1e-8:
        return [0.0] * len(samples)
    gain = float(peak) / loudest
    return [max(-1.0, min(1.0, float(sample) * gain)) for sample in samples]


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
    if sample_rate != target_rate:
        new_length = max(1, int(round(len(piece) * target_rate / sample_rate)))
        piece = resample(piece, new_length)
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
