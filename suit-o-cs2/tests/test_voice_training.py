"""Voice training session, profiles, and the clone backend. No microphone and no model."""

from __future__ import annotations

import sys
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.models import Utterance
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, SpeechConfig, load_config, parse_config
from suit_o.preferences import save_user_settings
from suit_o.speech.clone_backend import CloneSpeechBackend, cache_key
from suit_o.speech.factory import create_backend
from suit_o.speech.service import SpeechService
from suit_o.speech.stub import StubSpeechBackend
from suit_o.speech.tuning import VoiceTuning
from suit_o.voice.profile import clone_label, find_profile, is_clone_label, list_profiles, slugify
from suit_o.voice.runtime import INSTALL_HINT, runtime_status
from suit_o.voice.script import load_script
from suit_o.voice.session import RecordingSession, SessionError, silent_wav
from suit_o.voice.wav import excerpt, read_wav, shape_waveform, write_wav

JBL_MIC = "Headset Microphone (JBL Quantum 950X Wireless For Xbox Chat)"


def test_shipped_script_is_a_short_original_set():
    lines = load_script()
    assert 20 <= len(lines) <= 30
    assert any("Suit-O" in line for line in lines)
    assert all(not line.startswith("#") and line.strip() for line in lines)
    assert len(lines) == len(set(lines))


def test_script_skips_comments_and_blank_lines(tmp_path: Path):
    path = tmp_path / "voice_script.txt"
    path.write_text("# comment\n\nHello there.\n\n# hidden\nSecond line.\n", encoding="utf-8")
    assert load_script(path) == ["Hello there.", "Second line."]


def test_session_records_replays_and_builds_a_profile(tmp_path: Path):
    session = RecordingSession(["Alpha line.", "Beta line."], tmp_path / "takes")
    assert session.recorded_count == 0
    assert session.total == 2
    session.set_microphone(JBL_MIC)
    assert session.microphone == JBL_MIC

    try:
        session.stop_recording(silent_wav(1))
        stopped_early = False
    except SessionError:
        stopped_early = True
    assert stopped_early

    session.start_recording()
    try:
        session.start_recording()
        double = False
    except SessionError:
        double = True
    assert double
    session.stop_recording(silent_wav(25, 8000))
    assert session.state == "idle"
    assert session.recorded_count == 1
    assert session.has_take()

    session.rerecord()
    assert not session.has_take()
    session.start_recording()
    session.stop_recording(silent_wav(25, 8000))
    played = session.start_playback()
    assert played.is_file()
    session.finish_playback()
    assert session.state == "idle"

    session.next_line()
    assert session.index == 1
    try:
        session.build("Suit-O", tmp_path / "voices")
        built_early = False
    except SessionError as exc:
        built_early = True
        assert "1 of 2" in str(exc)
    assert built_early

    session.start_recording()
    session.stop_recording(silent_wav(25, 8000))
    profile = session.build("Suit-O", tmp_path / "voices")
    assert profile.name == "Suit-O"
    assert profile.slug == "suit-o"
    assert profile.model == "chatterbox"
    assert profile.reference_wav.is_file()
    assert profile.prompt_wav.is_file()
    assert profile.duration_seconds >= 45
    assert list_profiles(tmp_path / "voices") == [profile]
    assert find_profile(tmp_path / "voices", "suit-o").name == "Suit-O"
    assert clone_label(profile.name) == "Clone: Suit-O"
    assert is_clone_label("Clone: Suit-O")
    assert slugify("Suit-O") == "suit-o"


def test_waveform_pause_rate_and_pitch_stay_independent_of_the_model(tmp_path: Path):
    samples = [0.0, 0.2, -0.2, 0.4] * 40
    plain = shape_waveform(samples, 1000, VoiceTuning())
    assert plain == samples

    paused = shape_waveform(samples, 1000, VoiceTuning(pause_ms=1000))
    assert paused[:1000] == [0.0] * 1000
    assert paused[1000:] == samples

    faster = shape_waveform(samples, 1000, VoiceTuning(rate=370))
    assert len(faster) < len(samples)

    pitched = shape_waveform(samples, 1000, VoiceTuning(pitch=8))
    assert len(pitched) == len(samples)
    assert pitched != samples

    path = tmp_path / "tone.wav"
    write_wav(path, [0.0, 0.5, -0.5], 8000)
    loaded, rate = read_wav(path)
    assert rate == 8000
    assert len(loaded) == 3
    snippet = excerpt(list(range(100)), 10, 3)
    assert len(snippet) == 30


def test_clone_backend_is_selectable_without_the_optional_stack(tmp_path: Path):
    import suit_o.speech.clone_backend
    import suit_o.voice.runtime

    assert "torch" not in sys.modules
    assert "chatterbox" not in sys.modules
    status = runtime_status()
    assert status.installed is False
    assert status.device == "unavailable"
    assert "requirements-voice.txt" in status.summary
    assert "requirements-voice.txt" in INSTALL_HINT

    raw = __import__("yaml").safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["speech"]["backend"] = "clone"
    raw["speech"]["voice"] = "Suit-O"
    config = parse_config(raw)
    assert config.speech.backend == "clone"
    assert config.speech.voice == "Suit-O"

    settings = SpeechConfig(
        backend="clone",
        voice="Suit-O",
        rate=185,
        volume=0.5,
        output_device="",
        voices_dir=str(tmp_path / "voices"),
    )
    backend = create_backend(settings)
    assert isinstance(backend, CloneSpeechBackend)
    try:
        backend.set_output_device(JBL_MIC)
        refused = False
    except RuntimeError as exc:
        refused = True
        assert "microphone" in str(exc).lower()
    assert refused

    _write_profile(tmp_path / "voices")
    settings.voices_dir = str(tmp_path / "voices")
    missing = CloneSpeechBackend(settings)
    try:
        missing.speak("Hello")
        spoke = False
    except RuntimeError as exc:
        spoke = True
        assert "requirements-voice.txt" in str(exc)
    assert spoke


def test_clone_backend_caches_lines_and_preview_does_not_replace_the_live_backend(tmp_path: Path):
    voices = tmp_path / "voices"
    _write_profile(voices)
    calls: list[str] = []
    played: list[tuple[str, float]] = []

    def synthesize(text: str, prompt: Path, emphasis: str):
        calls.append(f"{emphasis}:{text}")
        return [0.2, -0.2, 0.2, -0.2], 8000

    def player(samples, rate, device, volume, cancel):
        del samples, rate, cancel
        played.append((device, volume))
        return True

    settings = SpeechConfig(
        backend="clone",
        voice="Suit-O",
        rate=185,
        volume=0.5,
        output_device="Headphones",
        voices_dir=str(voices),
    )
    backend = CloneSpeechBackend(settings, synthesizer=synthesize, player=player)
    assert backend.speak("Hello") is True
    assert backend.speak("Hello") is True
    assert calls == ["none:Hello"]
    assert played[-1] == ("Headphones", 0.5)

    tuned = VoiceTuning(voice="Suit-O", rate=160, pitch=2, pause_ms=40, emphasis="strong")
    assert cache_key("Hello", VoiceTuning()) != cache_key("Hello", tuned)
    backend.warm_stock_lines(["Cached line", "Hello"], wait=True)
    assert "none:Cached line" in calls
    assert calls.count("none:Hello") == 1

    stub = StubSpeechBackend()
    service = SpeechService(stub, preempt_min_priority=70)
    service.start()
    try:
        played_before = len(played)
        service.preview_with("preview clone", tuned, backend)
        assert service.wait_until(lambda: len(played) > played_before, 2)
        assert stub.spoken == []
        service.submit(Utterance("kill", "game", 36))
        assert service.wait_until(lambda: stub.spoken == ["game"], 2)
    finally:
        service.stop()


def test_app_keeps_stub_speech_until_a_real_clone_backend_is_requested(tmp_path: Path):
    voices = tmp_path / "voices"
    _write_profile(voices)
    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    made: list[CloneSpeechBackend] = []

    def factory(settings: SpeechConfig) -> CloneSpeechBackend:
        backend = CloneSpeechBackend(
            settings,
            synthesizer=lambda text, prompt, emphasis: ([0.1, -0.1], 8000),
            player=lambda samples, rate, device, volume, cancel: True,
        )
        made.append(backend)
        return backend

    config = load_config(DEFAULT_CONFIG_PATH)
    app = SuitOApp(
        config,
        backend=StubSpeechBackend(),
        config_path=path,
        voices_dir=voices,
        backend_factory=factory,
    )
    app.start()
    try:
        labels = app.voice_picker_labels()
        assert "Clone: Suit-O" in labels
        assert app.current_voice_label() != "Clone: Suit-O"
        applied = app.apply_saved_voice(VoiceTuning(rate=170, pitch=1, emphasis="mild"), "Clone: Suit-O")
        assert applied.voice == "Suit-O"
        assert app.config.speech.backend == "clone"
        assert app.speech.wait_until(lambda: isinstance(app.speech.backend, CloneSpeechBackend), 2)
        app.save_preferences()
    finally:
        app.stop()

    saved = load_config(path)
    assert saved.speech.backend == "clone"
    assert saved.speech.voice == "Suit-O"
    assert saved.speech.rate == 170
    assert saved.speech.pitch == 1
    assert saved.speech.emphasis == "mild"
    text = path.read_text(encoding="utf-8")
    assert "Do not set a microphone" in text
    assert made

    before = path.read_bytes()
    try:
        save_user_settings(path, backend="remote")
        refused = False
    except ConfigError:
        refused = True
    assert refused
    assert path.read_bytes() == before


def _write_profile(root: Path) -> None:
    folder = root / "suit-o"
    folder.mkdir(parents=True)
    tone = folder / "tone.wav"
    write_wav(tone, [0.0, 0.1, -0.1, 0.2], 8000)
    from suit_o.voice.profile import write_profile

    write_profile(root, "Suit-O", tone, tone, duration_seconds=50, sample_rate=8000)
