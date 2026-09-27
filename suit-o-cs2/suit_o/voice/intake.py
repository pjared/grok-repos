"""Turn existing recordings into training clips.

A file under 30 seconds becomes one normalized mono clip in the voice
library. A longer file is left for the Clips page to cut. Video and
compressed audio go through ffmpeg, the same path Clips already uses.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from collections.abc import Callable

from suit_o.voice.clips import ClipError, load_media
from suit_o.voice.library import ClipLibrary, ClipRecord
from suit_o.voice.passes import SpeakerTurn, diarize, isolate_speaker, separate_vocals

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


@dataclass(frozen=True)
class CleanedTake:
    """Audio after the shared Clips cleanup passes, before it joins the library."""

    samples: list[float]
    note: str
    speakers: tuple[str, ...] = ()
    turns: tuple[SpeakerTurn, ...] = ()


def run_cleanup(
    samples: list[float],
    sample_rate: int,
    *,
    separate: bool = False,
    pick_speaker: bool = False,
    token: str = "",
    separator=None,
    diarizer=None,
) -> CleanedTake:
    """Vocal separation, then speaker tags. Same functions the Clips page calls.

    One tagged speaker is kept here. Several speakers stay mixed until
    ``keep_speaker`` so the caller can ask which one.
    """

    audio = [float(sample) for sample in samples]
    notes: list[str] = []
    turns: tuple[SpeakerTurn, ...] = ()
    speakers: tuple[str, ...] = ()
    if separate:
        audio = [float(sample) for sample in separate_vocals(audio, sample_rate, separator=separator)]
        notes.append("Kept the vocal stem.")
    if pick_speaker:
        found = diarize(audio, sample_rate, token=token, diarizer=diarizer)
        turns = tuple(found)
        names: list[str] = []
        for turn in turns:
            if turn.speaker not in names:
                names.append(turn.speaker)
        if len(names) == 1:
            audio = isolate_speaker(audio, sample_rate, list(turns), names[0])
            notes.append(f"Kept {names[0]}.")
        elif names:
            speakers = tuple(names)
            notes.append("Tagged " + ", ".join(names) + ".")
        else:
            notes.append("No speakers were tagged.")
    return CleanedTake(samples=audio, note=" ".join(notes), speakers=speakers, turns=turns)


def keep_speaker(take: CleanedTake, speaker: str | None, sample_rate: int) -> CleanedTake:
    """Keep one tagged speaker. ``None`` leaves the mix in place."""

    chosen = (speaker or "").strip()
    if not chosen or chosen not in take.speakers:
        note = take.note
        if take.speakers:
            note = f"{note} Kept every speaker.".strip()
        return CleanedTake(samples=list(take.samples), note=note)
    audio = isolate_speaker(list(take.samples), sample_rate, list(take.turns), chosen)
    note = f"{take.note} Kept {chosen}.".strip()
    return CleanedTake(samples=audio, note=note)


def import_short_clip(
    path: Path,
    library: ClipLibrary,
    *,
    transcript: str = "",
    limit: float = SHORT_LIMIT_SECONDS,
    separate: bool = False,
    pick_speaker: bool = False,
    token: str = "",
    separator=None,
    diarizer=None,
    choose_speaker: Callable[[list[str]], str | None] | None = None,
    notes: list[str] | None = None,
) -> ClipRecord:
    """Convert one short recording into an included, normalized mono clip.

    ``separate`` and ``pick_speaker`` run the Clips cleanup passes first.
    ``separator`` and ``diarizer`` stand in for Demucs and pyannote in tests.
    """

    source = Path(path)
    samples, rate = load_media(source)
    duration = len(samples) / float(rate) if rate else 0.0
    if duration <= 0 or not samples:
        raise IntakeError(f"{source.name} has no audio")
    if duration >= float(limit):
        raise IntakeError(f"{source.name} is {duration:.0f}s. Open it in Clips to cut it.")
    if separate or pick_speaker:
        cleaned = run_cleanup(
            samples,
            rate,
            separate=separate,
            pick_speaker=pick_speaker,
            token=token,
            separator=separator,
            diarizer=diarizer,
        )
        if cleaned.speakers:
            choice = cleaned.speakers[0] if choose_speaker is None else choose_speaker(list(cleaned.speakers))
            cleaned = keep_speaker(cleaned, choice, rate)
        samples = cleaned.samples
        if notes is not None and cleaned.note:
            notes.append(cleaned.note)
        duration = len(samples) / float(rate) if rate else 0.0
        if duration <= 0 or not samples:
            raise IntakeError(f"{source.name} has no audio after cleanup")
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
