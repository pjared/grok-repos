"""Recording-session state for the Voice Training tab.

This module does not open a microphone. The window records audio and hands
the WAV bytes in. Tests can do the same with a silent buffer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from suit_o.voice.profile import ProfileError, VoiceProfile, write_profile
from suit_o.voice.wav import concat_wavs, excerpt, read_wav, wav_duration, write_wav

# About a minute of speech. The shipped script is meant to land near 1–3 minutes.
MIN_BUILD_SECONDS = 45.0
# Chatterbox clones from a reference clip. Longer than this hurts memory and
# does not help the model, so the prompt is an excerpt of the full recording.
PROMPT_SECONDS = 30.0


class SessionError(ValueError):
    """The recorder is in the wrong state for that button."""


@dataclass
class Take:
    index: int
    wav_path: Path
    duration_seconds: float


@dataclass
class RecordingSession:
    """One pass through the script. ``state`` is idle, recording, or playing."""

    lines: list[str]
    directory: Path
    index: int = 0
    state: str = "idle"
    microphone: str = ""
    takes: dict[int, Take] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.lines:
            raise SessionError("The voice script is empty")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.index = 0

    @property
    def total(self) -> int:
        return len(self.lines)

    @property
    def recorded_count(self) -> int:
        return sum(1 for index in range(self.total) if index in self.takes)

    @property
    def recorded_seconds(self) -> float:
        return sum(take.duration_seconds for take in self.takes.values())

    def line_text(self) -> str:
        return self.lines[self.index]

    def has_take(self, index: int | None = None) -> bool:
        chosen = self.index if index is None else index
        return chosen in self.takes

    def set_microphone(self, name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise SessionError("Choose a microphone")
        self.microphone = cleaned
        return cleaned

    def start_recording(self) -> None:
        if self.state == "recording":
            raise SessionError("Already recording")
        if self.state == "playing":
            raise SessionError("Stop playback before recording")
        self.state = "recording"

    def stop_recording(self, wav_bytes: bytes) -> Take:
        if self.state != "recording":
            raise SessionError("Nothing is recording")
        if not wav_bytes:
            self.state = "idle"
            raise SessionError("The recording was empty")
        path = self.directory / f"line-{self.index:02d}.wav"
        path.write_bytes(wav_bytes)
        try:
            duration = wav_duration(path)
        except Exception as exc:
            path.unlink(missing_ok=True)
            self.state = "idle"
            raise SessionError("That recording is not a readable WAV") from exc
        take = Take(self.index, path, duration)
        self.takes[self.index] = take
        self.state = "idle"
        return take

    def cancel_recording(self) -> None:
        """Drop back to idle when the microphone fails mid-take."""

        self.state = "idle"

    def start_playback(self) -> Path:
        if self.state == "recording":
            raise SessionError("Stop recording before playback")
        if self.state == "playing":
            raise SessionError("Already playing")
        take = self.takes.get(self.index)
        if take is None:
            raise SessionError("Record this line before playing it")
        self.state = "playing"
        return take.wav_path

    def finish_playback(self) -> None:
        if self.state == "playing":
            self.state = "idle"

    def rerecord(self) -> None:
        """Forget the take on the current line."""

        if self.state == "recording":
            raise SessionError("Stop recording before re-recording")
        if self.state == "playing":
            raise SessionError("Stop playback before re-recording")
        take = self.takes.pop(self.index, None)
        if take is not None and take.wav_path.is_file():
            take.wav_path.unlink()

    def goto(self, index: int) -> int:
        if self.state != "idle":
            raise SessionError("Stop recording or playback before changing lines")
        if index < 0 or index >= self.total:
            raise SessionError("That line is outside the script")
        self.index = index
        return self.index

    def next_line(self) -> int:
        return self.goto(min(self.total - 1, self.index + 1))

    def previous_line(self) -> int:
        return self.goto(max(0, self.index - 1))

    def missing_lines(self) -> list[int]:
        return [index for index in range(self.total) if index not in self.takes]

    def build(
        self,
        name: str,
        profiles_root: Path,
        *,
        extra_wavs: list[Path] | None = None,
    ) -> VoiceProfile:
        """Concatenate script takes and included library clips. Does not run the model.

        A full set of script lines still builds on its own. Included clips can
        stand in for lines that were chopped from one long take instead.
        """

        if self.state != "idle":
            raise SessionError("Stop recording or playback before building")
        extras = [Path(path) for path in (extra_wavs or []) if Path(path).is_file()]
        missing = self.missing_lines()
        if missing and not extras:
            raise SessionError(
                f"{len(missing)} script line(s) still need a recording "
                f"({self.recorded_count} of {self.total})"
            )
        ordered = [self.takes[index].wav_path for index in range(self.total) if index in self.takes]
        ordered.extend(extras)
        if not ordered:
            raise SessionError("Record the script or include clips from the library before building.")
        work = self.directory / "build"
        work.mkdir(parents=True, exist_ok=True)
        reference = work / "reference.wav"
        samples, rate = concat_wavs(ordered, reference)
        duration = len(samples) / float(rate) if rate else 0.0
        if duration < MIN_BUILD_SECONDS:
            raise SessionError(
                "Record about a minute of your own voice before building. "
                f"This set is {duration:.0f} seconds."
            )
        prompt = work / "prompt.wav"
        prompt_samples = excerpt(samples, rate, PROMPT_SECONDS)
        write_wav(prompt, prompt_samples, rate)
        try:
            return write_profile(
                profiles_root,
                name,
                reference,
                prompt,
                duration_seconds=duration,
                sample_rate=rate,
            )
        except ProfileError as exc:
            raise SessionError(str(exc)) from exc


def silent_wav(seconds: float, sample_rate: int = 16000) -> bytes:
    """A valid silent WAV, used by tests and as a stand-in buffer."""

    count = max(1, int(sample_rate * seconds))
    path_bytes = _wav_bytes([0.0] * count, sample_rate)
    return path_bytes


def _wav_bytes(samples: list[float], sample_rate: int) -> bytes:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        path = Path(folder) / "clip.wav"
        write_wav(path, samples, sample_rate)
        return path.read_bytes()


def peek_wav(wav_bytes: bytes) -> tuple[list[float], int]:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        path = Path(folder) / "clip.wav"
        path.write_bytes(wav_bytes)
        return read_wav(path)
