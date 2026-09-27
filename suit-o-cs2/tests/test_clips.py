"""Silence splits, clip export, and the per-voice clip library. No microphone."""

from __future__ import annotations

import wave
from array import array
from pathlib import Path

from suit_o.voice.clips import (
    delete_regions,
    export_clip,
    load_media,
    merge_regions,
    move_in,
    move_out,
    read_wav_mono,
    seek_time,
    split_on_silence,
    zoom_window,
)
from suit_o.voice.ffmpeg import FFMPEG_INSTALL, FfmpegError, require_ffmpeg, resolve_ffmpeg
from suit_o.voice.library import ClipLibrary, included_wavs
from suit_o.voice.runtime import MODEL_SAMPLE_RATE
from suit_o.voice.session import RecordingSession
from suit_o.voice.wav import read_wav, write_wav

RATE = 1000


def _tone(seconds: float, amplitude: float = 0.4) -> list[float]:
    count = int(RATE * seconds)
    return [amplitude if (index // 5) % 2 == 0 else -amplitude for index in range(count)]


def _silence(seconds: float) -> list[float]:
    return [0.0] * int(RATE * seconds)


def test_silence_split_respects_gap_length_and_minimum_clip():
    separated = _tone(0.8) + _silence(0.5) + _tone(0.8)
    regions = split_on_silence(separated, RATE, threshold=55, min_length=0.3, min_silence=0.3)
    assert len(regions) == 2
    assert regions[0][0] == 0
    assert 0.7 <= regions[0][1] <= 0.9
    assert regions[1][0] >= 1.2

    joined = _tone(0.8) + _silence(0.1) + _tone(0.8)
    assert len(split_on_silence(joined, RATE, threshold=55, min_length=0.3, min_silence=0.3)) == 1

    blip = _tone(0.1) + _silence(0.5) + _tone(0.8)
    kept = split_on_silence(blip, RATE, threshold=55, min_length=0.3, min_silence=0.3)
    assert len(kept) == 1
    assert kept[0][1] - kept[0][0] >= 0.7

    assert split_on_silence(separated, RATE, threshold=120, min_length=0.3, min_silence=0.2) == []
    assert split_on_silence([], RATE) == []

    merged = merge_regions([(0.0, 1.0), (1.2, 2.0), (3.0, 4.0)], [0, 2])
    assert merged == [(0.0, 4.0), (1.2, 2.0)]
    removed = delete_regions([(0.0, 1.0), (1.2, 2.0), (3.0, 4.0)], [1])
    assert removed == [(0.0, 1.0), (3.0, 4.0)]
    assert seek_time(1.0, -2.0, 5.0) == 0.0
    assert move_in(1.0, 2.0, 5.0) == 1.95
    assert move_out(1.0, 2.0, 10.0, 3.0) == 3.0
    assert zoom_window(0.0, 10.0, 10.0, 5.0, 0.5)[1] == 5.0


def test_export_normalizes_to_mono_at_the_model_rate(tmp_path: Path):
    samples = [0.5 if index % 2 == 0 else -0.25 for index in range(8000)]
    dest = tmp_path / "clip.wav"
    exported, rate = export_clip(samples, 8000, 0.0, 1.0, dest)
    assert rate == MODEL_SAMPLE_RATE
    assert dest.is_file()
    loaded, loaded_rate = read_wav(dest)
    assert loaded_rate == MODEL_SAMPLE_RATE
    assert abs(len(loaded) - MODEL_SAMPLE_RATE) <= 1
    peak = max(abs(sample) for sample in loaded)
    assert abs(peak - 0.89) < 0.02
    assert abs(exported[0] - loaded[0]) < 0.002

    stereo = tmp_path / "stereo.wav"
    _write_stereo(stereo, [10000, 10000, 20000, 20000], 8000)
    mixed, mixed_rate = read_wav_mono(stereo)
    assert mixed_rate == 8000
    assert len(mixed) == 2
    assert abs(mixed[0] - (10000 / 32767)) < 0.001
    assert abs(mixed[1]) > 0.5
    again, again_rate = load_media(dest)
    assert again_rate == MODEL_SAMPLE_RATE
    assert len(again) == len(loaded)


def test_library_metadata_include_and_build(tmp_path: Path):
    voices = tmp_path / "voices"
    library = ClipLibrary(voices, "Suit-O")
    tone = [0.4 if index % 2 == 0 else -0.4 for index in range(16000)]
    first = library.add_clip(tone, 8000, 0.0, 2.0, label="Window", transcript="Line one.", included=True)
    second = library.add_clip(tone, 8000, 0.0, 2.0, label="Ramp", transcript="", included=False)
    assert first.sample_rate == MODEL_SAMPLE_RATE
    assert (library.directory / first.filename).is_file()

    reloaded = ClipLibrary(voices, "Suit-O")
    assert [clip.id for clip in reloaded.clips()] == [first.id, second.id]
    assert abs(reloaded.included_duration() - first.duration_seconds) < 0.05
    renamed = reloaded.update(first.id, label="Window smoke", transcript="H-hey, window.")
    assert renamed.label == "Window smoke"
    assert renamed.transcript == "H-hey, window."
    assert ClipLibrary(voices, "Suit-O").clips()[0].transcript == "H-hey, window."
    reloaded.update(second.id, included=True)
    assert len(included_wavs(voices, "Suit-O")) == 2
    reloaded.delete(second.id)
    assert not (library.directory / second.filename).exists()
    assert [clip.id for clip in ClipLibrary(voices, "Suit-O").clips()] == [first.id]

    long = [0.2 if index % 2 == 0 else -0.2 for index in range(8000 * 50)]
    kept = library.add_clip(long, 8000, 0.0, 50.0, label="Take", transcript="Full script.", included=True)
    session = RecordingSession(["Alpha line.", "Beta line."], tmp_path / "takes")
    profile = session.build("Suit-O", voices, extra_wavs=included_wavs(voices, "Suit-O"))
    assert profile.slug == "suit-o"
    assert profile.duration_seconds >= 45
    assert (voices / "suit-o" / "clips" / kept.filename).is_file()
    assert (voices / "suit-o" / "profile.yaml").is_file()

    document = (voices / "suit-o" / "clips" / "library.json").read_text(encoding="utf-8")
    assert '"transcript": "Full script."' in document
    assert '"included": true' in document


def test_ffmpeg_resolver_prefers_path_and_explains_a_missing_binary(monkeypatch):
    assert resolve_ffmpeg("C:/ffmpeg/ffmpeg.exe", "C:/wheels/ffmpeg.exe") == "C:/ffmpeg/ffmpeg.exe"
    assert resolve_ffmpeg(None, "C:/wheels/ffmpeg.exe") == "C:/wheels/ffmpeg.exe"
    assert resolve_ffmpeg("", None) is None
    monkeypatch.setattr("suit_o.voice.ffmpeg.find_ffmpeg", lambda: None)
    try:
        require_ffmpeg()
    except FfmpegError as exc:
        assert "imageio-ffmpeg" in str(exc)
        assert "PATH" in str(exc)
        assert exc.args[0] == FFMPEG_INSTALL
    else:
        raise AssertionError("missing ffmpeg was accepted")


def _write_stereo(path: Path, samples: list[int], rate: int) -> None:
    payload = array("h", samples)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(payload.tobytes())
