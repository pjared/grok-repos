"""Tiny WAV read/write and waveform shaping. No audio libraries required."""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path

from suit_o.speech.tuning import DEFAULT_RATE, VoiceTuning, normalize_tuning

# Pitch ±10 maps to about ±3 semitones. Chatterbox has no pitch control of its own.
_PITCH_SEMITONES = 3.0


def write_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    """Write mono 16-bit PCM. Samples are floats in roughly ``-1`` … ``1``."""

    if sample_rate < 1:
        raise ValueError("sample rate must be positive")
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array("h", (_clamp_sample(sample) for sample in samples))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def read_wav(path: Path) -> tuple[list[float], int]:
    """Read a mono 16-bit WAV into float samples and its sample rate."""

    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if channels != 1 or width != 2:
        raise ValueError(f"{path} must be mono 16-bit WAV")
    pcm = array("h")
    pcm.frombytes(frames)
    return [sample / 32767.0 for sample in pcm], rate


def wav_duration(path: Path) -> float:
    samples, rate = read_wav(path)
    if rate < 1:
        return 0.0
    return len(samples) / float(rate)


def concat_wavs(paths: list[Path], destination: Path) -> tuple[list[float], int]:
    """Join mono WAVs. Later files are resampled to the first file's rate."""

    if not paths:
        raise ValueError("concat_wavs needs at least one file")
    first, rate = read_wav(paths[0])
    merged = list(first)
    for path in paths[1:]:
        samples, sample_rate = read_wav(path)
        if sample_rate != rate:
            samples = resample(samples, max(1, int(round(len(samples) * rate / sample_rate))))
        merged.extend(samples)
    write_wav(destination, merged, rate)
    return merged, rate


def excerpt(samples: list[float], sample_rate: int, seconds: float) -> list[float]:
    """Keep at most ``seconds`` of audio, starting one second in when possible."""

    if seconds <= 0 or not samples or sample_rate < 1:
        return []
    limit = max(1, int(sample_rate * seconds))
    if len(samples) <= limit:
        return list(samples)
    start = min(sample_rate, max(0, len(samples) - limit))
    return list(samples[start : start + limit])


def apply_volume(samples: list[float], volume: float) -> list[float]:
    gain = max(0.0, min(1.0, float(volume)))
    return [max(-1.0, min(1.0, sample * gain)) for sample in samples]


def shape_waveform(
    samples: list[float],
    sample_rate: int,
    tuning: VoiceTuning,
) -> list[float]:
    """Apply pitch, speaking rate, and a leading pause.

    Chatterbox does not expose pitch or words-per-minute. Pitch is a small
    resample, then rate changes the length. Volume is applied later, at
    playback, so the cache does not have to be rebuilt for a slider move.
    """

    tuning = normalize_tuning(tuning)
    shaped = list(samples)
    if tuning.pitch != 0 and len(shaped) >= 64:
        semitones = tuning.pitch * _PITCH_SEMITONES / 10.0
        shaped = pitch_shift(shaped, semitones)
    if tuning.rate != DEFAULT_RATE and shaped:
        target = max(1, int(round(len(shaped) * DEFAULT_RATE / tuning.rate)))
        shaped = resample(shaped, target)
    if tuning.pause_ms > 0 and sample_rate > 0:
        silence = [0.0] * int(sample_rate * tuning.pause_ms / 1000)
        shaped = silence + shaped
    return shaped


def pitch_shift(samples: list[float], semitones: float) -> list[float]:
    """Overlap-add pitch shift that keeps the length about the same."""

    if abs(semitones) < 0.01 or len(samples) < 64:
        return list(samples)
    ratio = 2 ** (semitones / 12.0)
    frame = 512 if len(samples) >= 512 else 64
    hop = frame // 4
    out = [0.0] * (len(samples) + frame)
    weight = [0.0] * len(out)
    pos = 0
    while pos < len(samples):
        grain = samples[pos : pos + frame]
        if len(grain) < hop:
            break
        shifted = resample(grain, max(8, int(round(len(grain) / ratio))))
        for index, sample in enumerate(shifted):
            at = pos + index
            if at >= len(out):
                break
            window = 0.5 - 0.5 * math.cos(2 * math.pi * index / max(1, len(shifted) - 1))
            out[at] += sample * window
            weight[at] += window
        pos += hop
    rendered: list[float] = []
    for index in range(len(samples)):
        if weight[index] > 1e-6:
            rendered.append(out[index] / weight[index])
        else:
            rendered.append(samples[index])
    return rendered


def resample(samples: list[float], new_length: int) -> list[float]:
    """Linear resample to ``new_length`` frames."""

    if new_length < 1:
        return []
    if not samples:
        return [0.0] * new_length
    if len(samples) == 1 or new_length == 1:
        return [samples[0]] * new_length
    scale = (len(samples) - 1) / (new_length - 1)
    out: list[float] = []
    last = len(samples) - 1
    for index in range(new_length):
        pos = index * scale
        left = int(pos)
        frac = pos - left
        right = left + 1 if left < last else last
        out.append(samples[left] * (1.0 - frac) + samples[right] * frac)
    return out


def _clamp_sample(sample: float) -> int:
    scaled = int(round(max(-1.0, min(1.0, float(sample))) * 32767))
    if scaled > 32767:
        return 32767
    if scaled < -32768:
        return -32768
    return scaled
