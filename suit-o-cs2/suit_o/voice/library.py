"""Local clip library, one folder per voice profile. Git ignores ``voices/``."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from suit_o.voice.clips import ClipError, export_clip
from suit_o.voice.profile import slugify
from suit_o.voice.runtime import MODEL_SAMPLE_RATE
from suit_o.voice.wav import read_wav

LIBRARY_VERSION = 1
LIBRARY_FILE = "library.json"


class LibraryError(ValueError):
    """Clip metadata could not be read or updated."""


@dataclass(frozen=True)
class ClipRecord:
    id: str
    filename: str
    label: str
    transcript: str
    included: bool
    duration_seconds: float
    sample_rate: int

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.filename,
            "label": self.label,
            "transcript": self.transcript,
            "included": self.included,
            "duration_seconds": round(float(self.duration_seconds), 3),
            "sample_rate": int(self.sample_rate),
        }


class ClipLibrary:
    """WAVs and ``library.json`` under ``voices/<slug>/clips/``."""

    def __init__(self, voices_root: Path, voice_name: str) -> None:
        self.voice_name = voice_name.strip() or "Suit-O"
        self.directory = Path(voices_root) / slugify(self.voice_name) / "clips"

    def clips(self) -> list[ClipRecord]:
        return _read_records(self.directory)

    def included_duration(self) -> float:
        return sum(clip.duration_seconds for clip in self.clips() if clip.included)

    def included_paths(self) -> list[Path]:
        paths: list[Path] = []
        for clip in self.clips():
            if not clip.included:
                continue
            path = self.directory / clip.filename
            if path.is_file():
                paths.append(path)
        return paths

    def add_clip(
        self,
        samples: list[float],
        sample_rate: int,
        start: float,
        end: float,
        *,
        label: str = "",
        transcript: str = "",
        included: bool = True,
    ) -> ClipRecord:
        self.directory.mkdir(parents=True, exist_ok=True)
        clip_id = uuid.uuid4().hex[:8]
        filename = f"{clip_id}.wav"
        dest = self.directory / filename
        _samples, rate = export_clip(samples, sample_rate, start, end, dest)
        duration = len(_samples) / float(rate) if rate else 0.0
        record = ClipRecord(
            id=clip_id,
            filename=filename,
            label=label.strip(),
            transcript=transcript.strip(),
            included=bool(included),
            duration_seconds=duration,
            sample_rate=rate,
        )
        rows = self.clips()
        rows.append(record)
        _write_records(self.directory, self.voice_name, rows)
        return record

    def update(
        self,
        clip_id: str,
        *,
        label: str | None = None,
        transcript: str | None = None,
        included: bool | None = None,
    ) -> ClipRecord:
        rows = self.clips()
        updated: ClipRecord | None = None
        rewritten: list[ClipRecord] = []
        for clip in rows:
            if clip.id != clip_id:
                rewritten.append(clip)
                continue
            updated = ClipRecord(
                id=clip.id,
                filename=clip.filename,
                label=clip.label if label is None else label.strip(),
                transcript=clip.transcript if transcript is None else transcript.strip(),
                included=clip.included if included is None else bool(included),
                duration_seconds=clip.duration_seconds,
                sample_rate=clip.sample_rate,
            )
            rewritten.append(updated)
        if updated is None:
            raise LibraryError(f"No clip named {clip_id}")
        _write_records(self.directory, self.voice_name, rewritten)
        return updated

    def delete(self, clip_id: str) -> None:
        rows = self.clips()
        kept: list[ClipRecord] = []
        removed: ClipRecord | None = None
        for clip in rows:
            if clip.id == clip_id:
                removed = clip
            else:
                kept.append(clip)
        if removed is None:
            raise LibraryError(f"No clip named {clip_id}")
        path = self.directory / removed.filename
        if path.is_file():
            path.unlink()
        _write_records(self.directory, self.voice_name, kept)


def included_wavs(voices_root: Path, voice_name: str) -> list[Path]:
    """Included clip files for Build voice. Missing libraries are an empty list."""

    try:
        return ClipLibrary(voices_root, voice_name).included_paths()
    except (LibraryError, ClipError, OSError):
        return []


def _read_records(directory: Path) -> list[ClipRecord]:
    path = directory / LIBRARY_FILE
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryError(f"Could not read {LIBRARY_FILE}: {exc}") from exc
    if not isinstance(raw, dict):
        raise LibraryError(f"{LIBRARY_FILE} must be a JSON object")
    rows = raw.get("clips")
    if not isinstance(rows, list):
        raise LibraryError(f"{LIBRARY_FILE} is missing clips")
    records: list[ClipRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        clip_id = str(row.get("id") or "").strip()
        filename = str(row.get("file") or "").strip()
        if not clip_id or not filename or "/" in filename or "\\" in filename or ".." in filename:
            continue
        try:
            duration = float(row.get("duration_seconds") or 0)
            rate = int(row.get("sample_rate") or MODEL_SAMPLE_RATE)
        except (TypeError, ValueError):
            continue
        wav_path = directory / filename
        if wav_path.is_file():
            try:
                _samples, file_rate = read_wav(wav_path)
                duration = len(_samples) / float(file_rate) if file_rate else duration
                rate = file_rate
            except (OSError, ValueError):
                pass
        records.append(
            ClipRecord(
                id=clip_id,
                filename=filename,
                label=str(row.get("label") or ""),
                transcript=str(row.get("transcript") or ""),
                included=bool(row.get("included", True)),
                duration_seconds=duration,
                sample_rate=rate,
            )
        )
    return records


def _write_records(directory: Path, voice_name: str, clips: list[ClipRecord]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": LIBRARY_VERSION,
        "voice": voice_name,
        "clips": [clip.as_dict() for clip in clips],
    }
    path = directory / LIBRARY_FILE
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
