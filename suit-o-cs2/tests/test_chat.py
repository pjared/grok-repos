"""Chat stays off the network, off disk, and out of a live round."""

from __future__ import annotations

import json
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from suit_o.app import SuitOApp
from suit_o.chat.availability import chat_is_paused
from suit_o.chat.idle import IDLE_RELEASE_SECONDS, IdleRelease
from suit_o.chat.llm import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    OLLAMA_SETUP,
    OPENAI_SETUP,
    ChatError,
    ChatSettings,
    load_chat_settings,
    release_model,
    stream_reply,
)
from suit_o.chat.persona import load_persona
from suit_o.chat.session import PAUSED, ChatSession
from suit_o.chat.stt import WHISPER_INSTALL, SttError, transcribe, whisper_available
from suit_o.config import DEFAULT_CONFIG_PATH, load_config
from suit_o.gui.chat import VRAM_NOTE, ChatPanel
from suit_o.local_config import local_config_path, store_personal_settings
from suit_o.reload import change_kind
from suit_o.speech.stub import StubSpeechBackend


def test_persona_reloads_and_replies_are_spoken_per_sentence(tmp_path: Path):
    persona = tmp_path / "persona.txt"
    persona.write_text("Be brief and original.", encoding="utf-8")
    session = ChatSession(persona_path=persona)
    seen: list[list[dict]] = []
    spoken: list[str] = []

    def generate(messages):
        seen.append(messages)
        yield "Hi. "
        yield "Sorry!"

    events = list(
        session.reply(
            "hello",
            paused=lambda: False,
            generate=generate,
            speak=spoken.append,
        )
    )
    assert spoken == ["Hi.", "Sorry!"]
    assert seen[0][0]["content"] == "Be brief and original."
    assert seen[0][-1] == {"role": "user", "content": "hello"}
    assert "".join(piece for kind, piece in events if kind == "token") == "Hi. Sorry!"
    persona.write_text("Even briefer.", encoding="utf-8")
    assert load_persona(persona) == "Even briefer."
    session.clear()
    assert session.turns == []

    def again(messages):
        seen.append(messages)
        yield "Ok."

    list(session.reply("next", paused=lambda: False, generate=again, speak=spoken.append))
    assert seen[-1][0]["content"] == "Even briefer."
    assert all(turn["content"] != "hello" for turn in seen[-1])


def test_live_match_does_not_call_the_model_or_speak():
    session = ChatSession()
    spoken: list[str] = []

    def generate(_messages):
        raise AssertionError("the model ran during a live match")
        yield ""

    events = list(session.reply("hello", paused=lambda: True, generate=generate, speak=spoken.append))
    assert events == [("status", PAUSED)]
    assert spoken == []
    assert session.turns == []


def test_clear_drops_the_reply_still_streaming():
    session = ChatSession()
    spoken: list[str] = []

    def generate(_messages):
        yield "Wait. "
        session.clear()
        yield "Still here."

    events = list(session.reply("go", paused=lambda: False, generate=generate, speak=spoken.append))
    assert spoken == ["Wait."]
    assert session.turns == []
    assert not any("Still" in piece for _kind, piece in events)


def test_stop_cuts_the_rest_of_the_reply():
    session = ChatSession()
    spoken: list[str] = []

    def generate(_messages):
        yield "Wait. "
        session.stop()
        yield "Keep going. "

    list(session.reply("go", paused=lambda: False, generate=generate, speak=spoken.append))
    assert spoken == ["Wait."]


def test_ollama_stream_is_local_and_a_dead_server_explains_setup():
    settings = ChatSettings("ollama", DEFAULT_OLLAMA_URL, DEFAULT_MODEL, "", "")
    calls: list[str] = []

    def post(url, payload, headers):
        calls.append(url)
        assert payload["model"] == DEFAULT_MODEL
        assert headers == {}
        yield json.dumps({"message": {"content": "Hi. "}, "done": False}) + "\n"
        yield json.dumps({"message": {"content": "Sorry!"}, "done": True}) + "\n"

    assert "".join(stream_reply(settings, [{"role": "user", "content": "hi"}], post=post)) == "Hi. Sorry!"
    assert calls == ["http://localhost:11434/api/chat"]

    def down(_url, _payload, _headers):
        raise OSError("connection refused")
        yield ""

    try:
        list(stream_reply(settings, [], post=down))
    except ChatError as exc:
        assert OLLAMA_SETUP in str(exc)
        assert "11434" in str(exc)
    else:
        raise AssertionError("a dead Ollama server was accepted")


def test_openai_key_stays_out_of_errors_and_the_tracked_config(tmp_path: Path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    local = local_config_path(config)
    local.write_text(
        "chat:\n  backend: openai\n  openai_url: http://127.0.0.1:9/v1\n  openai_key: sk-test-secret\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SUIT_O_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUIT_O_CHAT_BACKEND", raising=False)
    settings = load_chat_settings(config)
    assert settings.backend == "openai"
    assert settings.openai_key == "sk-test-secret"
    assert "sk-test-secret" not in DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")

    def post(url, _payload, headers):
        assert headers["Authorization"] == "Bearer sk-test-secret"
        assert url == "http://127.0.0.1:9/v1/chat/completions"
        raise OSError("upstream said sk-test-secret")
        yield ""

    try:
        list(stream_reply(settings, [], post=post))
    except ChatError as exc:
        message = str(exc)
        assert "sk-test-secret" not in message
        assert "[redacted]" in message
        assert OPENAI_SETUP in message
    else:
        raise AssertionError("the endpoint error was swallowed")

    store_personal_settings(config, volume=0.4)
    saved = local.read_text(encoding="utf-8")
    assert "sk-test-secret" in saved
    assert "sk-test-secret" not in config.read_text(encoding="utf-8")


def test_shipped_chat_defaults_and_persona_is_content():
    settings = load_chat_settings(DEFAULT_CONFIG_PATH)
    assert settings.backend == "ollama"
    assert settings.ollama_url == DEFAULT_OLLAMA_URL
    assert settings.model == DEFAULT_MODEL
    assert settings.openai_key == ""
    text = load_persona()
    assert "over-apologetic" in text
    assert "copyrighted" in text
    kind = change_kind(
        DEFAULT_CONFIG_PATH.parent / "lines" / "persona.txt",
        root=DEFAULT_CONFIG_PATH.parent,
        config_path=DEFAULT_CONFIG_PATH,
        lines_path=DEFAULT_CONFIG_PATH.parent / "lines" / "lines.yaml",
    )
    assert kind == "content"


def test_missing_whisper_explains_install_and_a_fake_transcriber_is_used(monkeypatch):
    monkeypatch.setattr("suit_o.chat.stt.whisper_available", lambda: False)
    try:
        transcribe([0.1, -0.1], 16000)
    except SttError as exc:
        assert "requirements-chat.txt" in str(exc)
        assert WHISPER_INSTALL in str(exc)
    else:
        raise AssertionError("missing faster-whisper was accepted")
    assert transcribe([0.1], 16000, transcriber=lambda _samples, _rate: "hello there") == "hello there"


def test_chat_panel_streams_text_and_pauses(tmp_path: Path):
    spoken: list[str] = []

    class _App:
        config_path = None

        def __init__(self) -> None:
            self.live = False

        def match_is_live(self) -> bool:
            return self.live

        def speak_chat(self, text: str) -> None:
            if self.live:
                raise AssertionError("spoke during a live match")
            spoken.append(text)

        def interrupt_chat(self) -> None:
            spoken.append("stopped")

    def generate(_messages):
        yield "Hi. "
        yield "Sorry!"

    root = tk.Tk()
    root.withdraw()
    try:
        app = _App()
        panel = ChatPanel(
            ttk.Frame(root),
            app,
            schedule=lambda callback: callback(),
            threaded=False,
            generate=generate,
        )
        assert "disabled" in panel.talk_button.state() or not whisper_available()
        panel.entry.insert(0, "hello")
        panel.send()
        shown = panel.history.get("1.0", "end")
        assert "You: hello" in shown
        assert "Hi. Sorry!" in shown
        assert spoken == ["Hi.", "Sorry!"]
        panel.clear()
        assert panel.history.get("1.0", "end").strip() == ""
        assert panel.session.turns == []
        app.live = True
        panel.entry.insert(0, "during the round")
        panel.send()
        assert panel.status.cget("text") == PAUSED
        assert spoken == ["Hi.", "Sorry!"]
        assert "during the round" not in panel.history.get("1.0", "end")
    finally:
        root.destroy()


def test_app_speaks_chat_on_the_device_and_not_during_a_round():
    config = load_config(DEFAULT_CONFIG_PATH)
    backend = StubSpeechBackend()
    app = SuitOApp(config, backend=backend)
    app.start()
    try:
        app.set_output_device("")
        app.speak_chat("Sorry about that.")
        assert app.speech.wait_until(lambda: backend.spoken == ["Sorry about that."], 2)
        assert not any("Sorry about that." in item.message for item in app.activity())
        app._match_activity = "playing"
        app._match_round = "live"
        app._match_map_phase = "live"
        app.speak_chat("Not during the round.")
        assert backend.spoken == ["Sorry about that."]
        assert app.match_is_live()
        app._match_map_phase = "warmup"
        app.speak_chat("Warmup is fine.")
        assert app.speech.wait_until(lambda: backend.spoken[-1] == "Warmup is fine.", 2)
        app._match_activity = "menu"
        app._match_map_phase = "live"
        app._match_round = "live"
        assert app.match_is_live() is False
    finally:
        app.stop()


def test_chat_allows_menu_warmup_and_the_gap_between_matches():
    assert chat_is_paused("playing", "live", "live") is True
    assert chat_is_paused("menu", "live", "live") is False
    assert chat_is_paused("playing", "live", "warmup") is False
    assert chat_is_paused("playing", "freezetime", "live") is False
    assert chat_is_paused("playing", None, None) is False
    assert chat_is_paused(None, None, None) is False


def test_idle_releases_a_resident_model_and_a_live_round_releases_it_now():
    calls: list[str] = []
    lease = IdleRelease(lambda: calls.append("gone"), wait=IDLE_RELEASE_SECONDS)
    assert lease.poll(IDLE_RELEASE_SECONDS, busy=False, paused=True) is False
    lease.touch(0)
    assert lease.poll(IDLE_RELEASE_SECONDS - 1, busy=False, paused=False) is False
    assert lease.poll(IDLE_RELEASE_SECONDS, busy=True, paused=False) is False
    assert lease.poll(IDLE_RELEASE_SECONDS * 2, busy=False, paused=False) is True
    assert calls == ["gone"]
    lease.touch(100)
    assert lease.poll(100, busy=False, paused=True) is True
    assert calls == ["gone", "gone"]


def test_ollama_release_unloads_without_sending_a_key_and_openai_does_not_call_out():
    settings = ChatSettings("ollama", DEFAULT_OLLAMA_URL, DEFAULT_MODEL, "", "")
    seen: list[tuple[str, dict]] = []

    def post(url, payload, headers):
        seen.append((url, payload))
        assert headers == {}
        assert "key" not in payload
        yield ""

    assert release_model(settings, post=post) is True
    assert seen == [(
        "http://localhost:11434/api/generate",
        {"model": DEFAULT_MODEL, "prompt": " ", "keep_alive": 0},
    )]

    remote = ChatSettings("openai", DEFAULT_OLLAMA_URL, "gpt-4o-mini", "http://127.0.0.1:9/v1", "sk-test")

    def boom(_url, _payload, _headers):
        raise AssertionError("a remote endpoint was asked to unload")
        yield ""

    assert release_model(remote, post=boom) is False


def test_chat_panel_shows_the_vram_note_and_releases_after_idle():
    released: list[str] = []

    class _App:
        config_path = None

        def match_is_live(self) -> bool:
            return False

        def speak_chat(self, _text: str) -> None:
            return None

        def interrupt_chat(self) -> None:
            return None

    root = tk.Tk()
    root.withdraw()
    try:
        panel = ChatPanel(
            ttk.Frame(root),
            _App(),
            schedule=lambda callback: callback(),
            threaded=False,
            generate=lambda _messages: iter(("Ok.",)),
            on_release=lambda: released.append("yes"),
        )
        assert panel.vram_note.cget("text") == VRAM_NOTE
        assert "7 to 9 GB" in VRAM_NOTE
        panel._idle.touch(0)
        assert panel.poll_idle(now=IDLE_RELEASE_SECONDS) is True
        assert released == ["yes"]
    finally:
        root.destroy()
