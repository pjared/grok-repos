"""Turn existing recordings into training clips.

A file under 30 seconds becomes one normalized mono clip in the voice
library. A longer file is left for the Clips page to cut. Video and
compressed audio go through ffmpeg, the same path Clips already uses.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from suit_o.voice.clips import ClipError, load_media
from suit_o.voice.library import ClipLibrary, ClipRecord

# "Under about 30 s" joins the library as one clip. Longer takes open in Clips.
SHORT_LIMIT_SECONDS = 30.0

AUDIO_SUFFIXES = frozenset({".wav", ".mp3", ".m4a", ".flac", ".ogg"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"})
MEDIA_SUFFIXES = AUDIO_SUFFIXES | VIDEO_SUFFIXES


class IntakeError(ValueError):
    """A recording could not be added to the library."""


@dataclass(frozen=True)
class IntakeItem:
    path: Path
    kind: str
    detail: str = ""


def classify_path(path: Path, *, limit: float = SHORT_LIMIT_SECONDS) -> IntakeItem:
    """``short``, ``long``, or ``rejected``. Does not copy the file."""

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        return IntakeItem(source, "rejected", f"{source.name} is not a recording Suit-O can open")
    if not source.is_file():
        return IntakeItem(source, "rejected", f"File not found: {source.name}")
    try:
        duration = media_duration(source)
    except (ClipError, OSError, RuntimeError) as exc:
        return IntakeItem(source, "rejected", str(exc))
    if duration <= 0:
        return IntakeItem(source, "rejected", f"{source.name} has no audio")
    if duration < float(limit):
        return IntakeItem(source, "short")
    return IntakeItem(source, "long")


def media_duration(path: Path) -> float:
    """Length in seconds. WAV uses the header. Everything else uses ffmpeg."""

    source = Path(path)
    if source.suffix.lower() == ".wav":
        try:
            return _wav_seconds(source)
        except (OSError, wave.Error, ClipError):
            pass
    from suit_o.voice.ffmpeg import probe_duration

    return probe_duration(source)


def import_short_clip(
    path: Path,
    library: ClipLibrary,
    *,
    transcript: str = "",
    limit: float = SHORT_LIMIT_SECONDS,
) -> ClipRecord:
    """Convert one short recording into an included, normalized mono clip."""

    source = Path(path)
    samples, rate = load_media(source)
    duration = len(samples) / float(rate) if rate else 0.0
    if duration <= 0 or not samples:
        raise IntakeError(f"{source.name} has no audio")
    if duration >= float(limit):
        raise IntakeError(f"{source.name} is {duration:.0f}s. Open it in Clips to cut it.")
    label = source.stem.replace("_", " ").replace("-", " ").strip() or "Clip"
    return library.add_clip(
        samples,
        rate,
        0.0,
        duration,
        label=label,
        transcript=transcript,
        included=True,
    )


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        frames = handle.getnframes()
    if rate < 1 or frames < 1:
        raise ClipError(f"{path.name} has no audio")
    return frames / float(rate)
