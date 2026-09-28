"""Find ffmpeg and turn a long recording into a WAV.

Windows can use the ffmpeg binary shipped in the ``imageio-ffmpeg`` wheel.
A copy already on PATH wins. The base Suit-O install does not require either.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from suit_o.procs import hidden_window_kwargs

FFMPEG_INSTALL = (
    "Suit-O needs ffmpeg to open that recording. "
    "From the suit-o-cs2 folder run: python -m pip install -r requirements-voice.txt "
    "(that installs the imageio-ffmpeg wheel, which bundles ffmpeg on Windows). "
    "Or install ffmpeg yourself and put it on PATH."
)


class FfmpegError(RuntimeError):
    """ffmpeg is missing or could not read the file."""


def resolve_ffmpeg(on_path: str | None, bundled: str | None) -> str | None:
    """Prefer an ffmpeg already on PATH, then a bundled wheel binary."""

    if on_path and on_path.strip():
        return on_path.strip()
    if bundled and bundled.strip():
        return bundled.strip()
    return None


def find_ffmpeg() -> str | None:
    return resolve_ffmpeg(shutil.which("ffmpeg"), _imageio_ffmpeg())


def require_ffmpeg() -> str:
    exe = find_ffmpeg()
    if not exe:
        raise FfmpegError(FFMPEG_INSTALL)
    return exe


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe_duration(source: Path) -> float:
    """Seconds of audio or video, from the file header. Does not decode it."""

    if not source.is_file():
        raise FfmpegError(f"File not found: {source}")
    exe = require_ffmpeg()
    try:
        completed = subprocess.run(
            [exe, "-hide_banner", "-i", str(source)],
            capture_output=True,
            check=False,
            **hidden_window_kwargs(),
        )
    except OSError as exc:
        raise FfmpegError(FFMPEG_INSTALL) from exc
    text = completed.stderr.decode("utf-8", errors="replace")
    match = _DURATION.search(text)
    if not match:
        raise FfmpegError(f"Could not read the length of {source.name}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def extract_audio(source: Path, dest: Path, *, sample_rate: int) -> None:
    """Write a mono 16-bit WAV. ``source`` may be audio or video."""

    if not source.is_file():
        raise FfmpegError(f"File not found: {source}")
    exe = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        exe,
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(int(sample_rate)),
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, check=False, **hidden_window_kwargs())
    except OSError as exc:
        raise FfmpegError(FFMPEG_INSTALL) from exc
    if completed.returncode != 0 or not dest.is_file():
        detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        tail = detail[-1] if detail else "ffmpeg failed"
        raise FfmpegError(f"Could not read {source.name}. {tail}")


def _imageio_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    if exe and Path(exe).is_file():
        return str(exe)
    return None
