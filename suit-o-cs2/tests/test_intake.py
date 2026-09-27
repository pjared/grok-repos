"""Existing recordings join a voice library, or open in Clips when they are long."""

from __future__ import annotations

import wave
from pathlib import Path

from tkinter import ttk

from tkutil import open_tk_or_skip

from suit_o.gui.drops import parse_dropped_files
from suit_o.gui.training import CONSENT, TrainingPanel
from suit_o.voice.intake import SHORT_LIMIT_SECONDS, classify_path, import_short_clip
from suit_o.voice.library import ClipLibrary, included_wavs
from suit_o.voice.script import load_script
from suit_o.voice.session import RecordingSession
from suit_o.voice.wav import read_wav, write_wav


def _tone(path: Path, seconds: float, *, rate: int = 8000, amplitude: float = 0.25, channels: int = 1) -> None:
    count = max(1, int(rate * seconds))
    path.parent.mkdir(parents=True, exist_ok=True)
    if channels == 1:
        write_wav(path, [amplitude] * count, rate)
        return
    import array

    pcm = array.array("h", [int(amplitude * 32767)] * (count * channels))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def test_short_wav_becomes_a_normalized_mono_clip_and_a_long_one_does_not(tmp_path: Path):
    short = tmp_path / "hello there.wav"
    long = tmp_path / "full-take.wav"
    stereo = tmp_path / "both-ears.wav"
    _tone(short, 1.2, amplitude=0.2)
    _tone(long, SHORT_LIMIT_SECONDS + 1)
    _tone(stereo, 0.4, channels=2, amplitude=0.15)
    notes = tmp_path / "notes.txt"
    notes.write_text("nope", encoding="utf-8")

    assert classify_path(short).kind == "short"
    assert classify_path(long).kind == "long"
    assert classify_path(stereo).kind == "short"
    assert classify_path(notes).kind == "rejected"

    voices = tmp_path / "voices"
    library = ClipLibrary(voices, "Suit-O")
    added = import_short_clip(short, library, transcript="H-hey, window.")
    stereo_clip = import_short_clip(stereo, library, transcript="")
    assert added.transcript == "H-hey, window."
    assert added.included is True
    samples, rate = read_wav(library.directory / added.filename)
    assert rate == 24000
    assert max(abs(sample) for sample in samples) == pytest_peak(samples)
    mixed, mixed_rate = read_wav(library.directory / stereo_clip.filename)
    assert mixed_rate == 24000
    assert mixed
    edited = library.update(added.id, transcript="Sorry, window.")
    assert edited.transcript == "Sorry, window."
    assert len(included_wavs(voices, "Suit-O")) == 2

    session = RecordingSession(load_script(), tmp_path / "session")
    try:
        session.build("Suit-O", voices, extra_wavs=included_wavs(voices, "Suit-O"))
        raised = False
    except Exception as exc:
        raised = True
        assert "minute" in str(exc).lower() or "seconds" in str(exc).lower()
    assert raised


def pytest_peak(samples: list[float]) -> float:
    peak = max(abs(sample) for sample in samples)
    assert abs(peak - 0.89) < 0.02
    return peak


def test_compressed_audio_uses_the_ffmpeg_duration_and_loader(tmp_path: Path, monkeypatch):
    source = tmp_path / "line.mp3"
    source.write_bytes(b"not a real mp3")
    monkeypatch.setattr("suit_o.voice.ffmpeg.probe_duration", lambda path: 4.0)
    monkeypatch.setattr(
        "suit_o.voice.intake.load_media",
        lambda path: ([0.2] * 8000, 8000),
    )
    assert classify_path(source).kind == "short"
    clip = import_short_clip(source, ClipLibrary(tmp_path / "voices", "Suit-O"), transcript="From a file.")
    assert clip.transcript == "From a file."
    assert clip.duration_seconds > 0

    monkeypatch.setattr("suit_o.voice.ffmpeg.probe_duration", lambda path: 48.0)
    movie = tmp_path / "match.mp4"
    movie.write_bytes(b"video")
    assert classify_path(movie).kind == "long"


def test_dropped_paths_keep_spaces_and_the_training_tab_imports_them(tmp_path: Path):
    first = tmp_path / "my clip.wav"
    second = tmp_path / "other.ogg"
    _tone(first, 0.5)
    parsed = parse_dropped_files(f"{{{first}}} {second}")
    assert parsed == [first, second]

    longs: list[Path] = []

    class _App:
        def __init__(self) -> None:
            self.voices_dir = tmp_path / "voices"

    root = open_tk_or_skip()
    try:
        panel = TrainingPanel(
            ttk.Frame(root),
            _App(),
            on_profile_built=lambda _name: None,
            schedule=lambda callback: None,
            on_long_file=longs.append,
        )
        assert CONSENT.startswith("Record your own voice")
        long = tmp_path / "long-take.wav"
        _tone(long, SHORT_LIMIT_SECONDS)
        panel.import_paths(
            [first, long, tmp_path / "nope.txt"],
            transcripts={first.name: "Added from a drop."},
            ask_transcript=False,
        )
        library = ClipLibrary(panel.app.voices_dir, "Suit-O")
        assert [clip.transcript for clip in library.clips()] == ["Added from a drop."]
        assert "Usable:" in panel.library_label.cget("text")
        assert library.included_duration() > 0
        assert "usable" in panel.progress.cget("text")
        assert longs == [long]
        assert "Clips" in panel.status.cget("text")
        assert "nope.txt" in panel.status.cget("text")
    finally:
        root.destroy()


def test_short_upload_runs_the_clips_cleanup_passes(tmp_path: Path):
    source = tmp_path / "booth.wav"
    _tone(source, 1.0, rate=8000, amplitude=0.2)

    def separator(samples, rate):
        assert len(samples) == rate
        return [0.4] * rate

    def diarizer(_samples, rate):
        class _Turn:
            def __init__(self, speaker: str, start: float, end: float) -> None:
                self.speaker = speaker
                self.start = start
                self.end = end

        assert rate == 8000
        return [_Turn("A", 0.0, 0.5), _Turn("B", 0.5, 1.0)]

    notes: list[str] = []
    record = import_short_clip(
        source,
        ClipLibrary(tmp_path / "voices", "Suit-O"),
        transcript="cleaned",
        separate=True,
        pick_speaker=True,
        token="hf-test-token",
        separator=separator,
        diarizer=diarizer,
        choose_speaker=lambda names: "B" if names == ["A", "B"] else None,
        notes=notes,
    )
    assert record.transcript == "cleaned"
    text = " ".join(notes)
    assert "vocal stem" in text
    assert "Kept B" in text
    assert "hf-test-token" not in text
    samples, rate = read_wav(ClipLibrary(tmp_path / "voices", "Suit-O").included_paths()[0])
    assert rate > 0
    early = samples[: len(samples) // 4]
    late = samples[(3 * len(samples)) // 4 :]
    assert max(abs(sample) for sample in early) < 0.05
    assert max(abs(sample) for sample in late) > 0.5


def test_training_cleanup_checks_use_the_clips_passes(tmp_path: Path, monkeypatch):
    from suit_o.voice.passes import demucs_available

    source = tmp_path / "booth.wav"
    _tone(source, 0.4, rate=8000, amplitude=0.2)

    class _App:
        def __init__(self) -> None:
            self.voices_dir = tmp_path / "voices"
            self.config_path = None

    root = open_tk_or_skip()
    try:
        panel = TrainingPanel(
            ttk.Frame(root),
            _App(),
            on_profile_built=lambda _name: None,
            schedule=lambda callback: callback(),
        )
        if not demucs_available():
            assert "disabled" in panel.separate_check.state()
            assert "requirements-clips.txt" in panel.cleanup_hint.cget("text")
        monkeypatch.setattr("suit_o.voice.passes.demucs_status", lambda: (True, ""))
        monkeypatch.setattr("suit_o.voice.passes.pyannote_status", lambda: (True, ""))
        monkeypatch.setattr("suit_o.voice.passes.read_hf_token", lambda _path: "hf-test")
        panel._paint_cleanup()
        assert "disabled" not in panel.separate_check.state()
        assert "disabled" not in panel.pick_check.state()
        panel.separate_var.set(True)
        panel.pick_var.set(True)
        panel._async_cleanup = False
        panel._separator = lambda _samples, rate: [0.3] * rate
        panel._diarizer = lambda _samples, _rate: [_Speaker("A", 0.0, 0.4)]
        panel._choose_speaker = lambda names: (_ for _ in ()).throw(AssertionError(names))
        panel.import_paths([source], transcripts={source.name: "one speaker"}, ask_transcript=False)
        assert "Kept A" in panel.status.cget("text")
        assert "one speaker" in [
            clip.transcript for clip in ClipLibrary(panel.app.voices_dir, "Suit-O").clips()
        ]
    finally:
        root.destroy()


class _Speaker:
    def __init__(self, speaker: str, start: float, end: float) -> None:
        self.speaker = speaker
        self.start = start
        self.end = end
