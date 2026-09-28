"""Chat with a cloned voice: the model stays loaded and sentences render ahead.

No Tk window, no microphone, and no voice model. The synthesizer and player are
fakes, so these run on a CI runner with no display.
"""

from __future__ import annotations

import threading
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, SpeechConfig, load_config
from suit_o.speech.chat_render import ChatRenderer
from suit_o.speech.clone_backend import CloneSpeechBackend
from suit_o.speech.stub import StubSpeechBackend
from suit_o.voice import engine as voice_engine
from suit_o.voice import runtime as voice_runtime
from suit_o.voice.runtime import RuntimeStatus
from suit_o.voice.wav import write_wav


def _write_profile(root: Path) -> None:
    folder = root / "suit-o"
    folder.mkdir(parents=True)
    tone = folder / "tone.wav"
    write_wav(tone, [0.0, 0.1, -0.1, 0.2], 8000)
    from suit_o.voice.profile import write_profile

    write_profile(root, "Suit-O", tone, tone, duration_seconds=50, sample_rate=8000)


def _settings(voices: Path) -> SpeechConfig:
    return SpeechConfig(
        backend="clone",
        voice="Suit-O",
        rate=185,
        volume=0.5,
        output_device="Headphones",
        voices_dir=str(voices),
    )


def test_renderer_keeps_order_and_discard_drops_what_has_not_started():
    gate = threading.Event()
    order: list[str] = []

    def render(text: str):
        if text == "first":
            gate.wait(2)
        order.append(text)
        return [0.0], 8000

    renderer = ChatRenderer()
    try:
        first = renderer.render("first", render)
        second = renderer.render("second", render)
        third = renderer.render("third", render)
        assert renderer.discard() == 2
        assert second.cancelled() and third.cancelled()
        gate.set()
        assert first.result(timeout=2) == ([0.0], 8000)
        again = renderer.render("again", render)
        assert again.result(timeout=2) == ([0.0], 8000)
        assert order == ["first", "again"]
    finally:
        renderer.close()


def test_live_chat_line_keeps_the_model_loaded_and_plays_the_early_render(tmp_path: Path, monkeypatch):
    voices = tmp_path / "voices"
    _write_profile(voices)
    released: list[bool] = []
    monkeypatch.setattr(voice_engine, "release_model", lambda: released.append(True))
    synthesized: list[str] = []
    played: list[list[float]] = []

    def synthesize(text: str, prompt: Path, emphasis: str):
        synthesized.append(text)
        return [0.25, -0.25], 8000

    def player(samples, rate, device, volume, cancel):
        played.append(list(samples))
        return True

    backend = CloneSpeechBackend(_settings(voices), synthesizer=synthesize, player=player)
    backend.allow_live_synthesis()
    backend.keep_model_loaded()
    renderer = ChatRenderer()
    try:
        backend.use_rendered(renderer.render("Hello there.", backend.render_live))
        assert backend.speak("Hello there.") is True
    finally:
        renderer.close()
    assert synthesized == ["Hello there."]
    assert len(played) == 1
    assert released == []

    preview = CloneSpeechBackend(_settings(voices), synthesizer=synthesize, player=player)
    preview.allow_live_synthesis()
    assert preview.speak("A Voice tab preview.") is True
    assert released == [True]


def test_stop_abandons_a_render_that_is_still_running(tmp_path: Path, monkeypatch):
    voices = tmp_path / "voices"
    _write_profile(voices)
    monkeypatch.setattr(voice_engine, "release_model", lambda: None)
    gate = threading.Event()
    played: list[int] = []

    def synthesize(text: str, prompt: Path, emphasis: str):
        gate.wait(2)
        return [0.1], 8000

    backend = CloneSpeechBackend(
        _settings(voices),
        synthesizer=synthesize,
        player=lambda samples, rate, device, volume, cancel: played.append(1) or True,
    )
    backend.allow_live_synthesis()
    backend.keep_model_loaded()
    renderer = ChatRenderer()
    try:
        backend.use_rendered(renderer.render("Slow line.", backend.render_live))
        result: list[bool] = []
        speaker = threading.Thread(target=lambda: result.append(backend.speak("Slow line.")))
        speaker.start()
        backend.stop()
        speaker.join(timeout=2)
        gate.set()
        assert result == [False]
        assert played == []
    finally:
        renderer.close()


def test_app_renders_each_chat_sentence_ahead_and_releases_when_asked(tmp_path: Path, monkeypatch):
    voices = tmp_path / "voices"
    _write_profile(voices)
    monkeypatch.setattr(
        voice_runtime,
        "runtime_status",
        lambda: RuntimeStatus(installed=True, device="cpu", summary="CPU"),
    )
    released: list[bool] = []
    monkeypatch.setattr(voice_engine, "release_model", lambda: released.append(True))
    rendered: list[str] = []
    played: list[str] = []
    lock = threading.Lock()

    def synthesize(text: str, prompt: Path, emphasis: str):
        with lock:
            rendered.append(text)
        return [0.1, -0.1], 8000

    def factory(settings: SpeechConfig) -> CloneSpeechBackend:
        backend = CloneSpeechBackend(
            settings,
            synthesizer=synthesize,
            player=lambda samples, rate, device, volume, cancel: True,
        )
        original = backend.speak

        def speak(text, tuning=None):
            ok = original(text, tuning)
            if ok:
                played.append(text)
            return ok

        backend.speak = speak  # type: ignore[method-assign]
        return backend

    config = load_config(DEFAULT_CONFIG_PATH)
    config.speech.backend = "clone"
    config.speech.voice = "Suit-O"
    app = SuitOApp(
        config,
        backend=StubSpeechBackend(),
        config_path=tmp_path / "config.yaml",
        voices_dir=voices,
        backend_factory=factory,
    )
    app.start()
    try:
        app.speak_chat("Oh. Hi.")
        app.speak_chat("I was just standing here.")
        app.speak_chat("Loudly.")
        assert app.speech.wait_until(lambda: len(played) == 3, 3)
        assert played == ["Oh. Hi.", "I was just standing here.", "Loudly."]
        assert rendered == played
        assert released == []
        app.release_chat_voice()
        assert released == [True]
    finally:
        app.stop()
