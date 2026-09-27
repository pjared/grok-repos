"""Speech queue preemption and playback-device selection."""

from __future__ import annotations

import logging
import sys
import threading
from types import SimpleNamespace

from suit_o.config import SpeechConfig, is_disallowed_output_device
from suit_o.models import Utterance
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.devices import (
    DeviceSelectionError,
    enumerate_sapi_playback_devices,
    list_output_device_names,
    match_voice,
    select_output_token,
)
from suit_o.speech.factory import create_backend
from suit_o.speech.pyttsx3_backend import Pyttsx3Backend
from suit_o.speech.remote import RemoteTtsBackend
from suit_o.speech.service import SpeechService
from suit_o.speech.stub import StubSpeechBackend

# Names SAPI reports on the machine this was built for. The fourth endpoint
# is the monitor. The microphone is the recording side of the same headset
# and must never be selected.
JBL_GAME = "Speakers (JBL Quantum 950X Wireless For Xbox Game)"
JBL_CHAT = "Headset Earphone (JBL Quantum 950X Wireless For Xbox Chat)"
REALTEK = "Realtek Digital Output"
MONITOR = "LG ULTRAGEAR (NVIDIA High Definition Audio)"
JBL_MIC = "Headset Microphone (JBL Quantum 950X Wireless For Xbox Chat)"


class GateBackend(SpeechBackend):
    """First speak blocks until stop()."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.results: list[tuple[str, str]] = []
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self.calls = 0

    def speak(self, text: str) -> bool:
        with self._lock:
            self.calls += 1
            call = self.calls
        if call == 1:
            self.started.set()
            cancelled = self._cancel.wait(timeout=2)
            self.results.append(("cut" if cancelled else "timeout", text))
            self._cancel.clear()
            return not cancelled
        if self._cancel.is_set():
            self._cancel.clear()
            self.results.append(("cut", text))
            return False
        self.results.append(("ok", text))
        return True

    def stop(self) -> None:
        self._cancel.set()

    def close(self) -> None:
        self._cancel.set()


class HoldBackend(SpeechBackend):
    """First speak blocks until release(), and records unexpected stop() calls."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.spoken: list[str] = []
        self.stops = 0

    def speak(self, text: str) -> bool:
        self.spoken.append(text)
        if len(self.spoken) == 1:
            self.started.set()
            self.release.wait(timeout=2)
        return True

    def stop(self) -> None:
        self.stops += 1
        self.release.set()

    def close(self) -> None:
        self.release.set()


def test_big_moment_interrupts_a_smaller_line():
    backend = GateBackend()
    service = SpeechService(backend, preempt_min_priority=70)
    service.start()
    try:
        service.submit(Utterance("warmup", "small talk", 14))
        assert backend.started.wait(2)
        service.submit(Utterance("ace", "ace line", 100))
        assert service.wait_until(lambda: len(service.history) >= 1, 2)
        assert [item.event_type for item in service.history] == ["ace"]
        assert ("cut", "small talk") in backend.results
        assert ("ok", "ace line") in backend.results
    finally:
        service.stop()


def test_medium_line_does_not_interrupt():
    backend = HoldBackend()
    service = SpeechService(backend, preempt_min_priority=70)
    service.start()
    try:
        service.submit(Utterance("kill", "one", 36))
        assert backend.started.wait(2)
        service.submit(Utterance("round_won", "two", 60))
        assert backend.stops == 0
        backend.release.set()
        assert service.wait_until(lambda: len(service.history) == 2, 2)
        assert [item.text for item in service.history] == ["one", "two"]
    finally:
        service.stop()


def test_mute_drops_queued_speech():
    backend = HoldBackend()
    service = SpeechService(backend, preempt_min_priority=70)
    service.start()
    try:
        service.submit(Utterance("warmup", "hello", 14))
        assert backend.started.wait(2)
        service.submit(Utterance("kill", "later", 36))
        service.set_muted(True)
        backend.release.set()
        assert service.wait_until(lambda: True, 2)
        assert [item.text for item in service.history] == []
    finally:
        service.stop()


def test_remote_backend_is_not_implemented():
    settings = SpeechConfig(
        backend="remote",
        voice="",
        rate=185,
        volume=1.0,
        output_device="",
    )
    try:
        create_backend(settings)
        raised = False
    except NotImplementedError as exc:
        raised = True
        assert "not implemented" in str(exc).lower()
        assert "voice chat" in str(exc).lower()
    assert raised
    try:
        RemoteTtsBackend(settings)
        raised_direct = False
    except NotImplementedError:
        raised_direct = True
    assert raised_direct


def test_voice_and_device_matching():
    assert match_voice([("Microsoft David", "david")], "") is None
    assert match_voice([("Microsoft David", "david"), ("Microsoft Zira", "zira")], "zira") == "zira"
    try:
        match_voice([("Microsoft David", "david")], "Zira")
        missed = False
    except DeviceSelectionError:
        missed = True
    assert missed

    chosen = select_output_token(
        [("Speakers", "speakers"), ("Headset Earphone", "phones")],
        "headset",
    )
    assert chosen == "phones"
    assert is_disallowed_output_device("CABLE Input")
    assert is_disallowed_output_device("Headset Microphone")
    assert is_disallowed_output_device("VB-Audio Virtual Cable")
    assert not is_disallowed_output_device("Headset Earphone")
    assert not is_disallowed_output_device("")
    assert not is_disallowed_output_device(JBL_GAME)
    assert not is_disallowed_output_device(JBL_CHAT)
    assert not is_disallowed_output_device(REALTEK)
    assert not is_disallowed_output_device(MONITOR)
    assert is_disallowed_output_device(JBL_MIC)

    chat = select_output_token(
        [(JBL_GAME, "game"), (JBL_CHAT, "chat"), (REALTEK, "realtek"), (MONITOR, "monitor")],
        JBL_CHAT,
    )
    assert chat == "chat"
    exact = select_output_token(
        [("Speakers", "short"), (JBL_GAME, "game")],
        "Speakers",
    )
    assert exact == "short"


def test_volume_and_device_apply_before_the_line_and_test_voice_bypasses_mute():
    backend = StubSpeechBackend()
    service = SpeechService(backend, preempt_min_priority=70)
    service.start()
    try:
        service.set_volume(0.25)
        service.set_output_device(REALTEK)
        service.set_muted(True)
        service.submit(Utterance("kill", "nope", 36))
        service.submit(Utterance("test", "can you hear this", 100), bypass_mute=True)
        assert service.wait_until(lambda: backend.spoken == ["can you hear this"], 2)
        assert backend.volume == 0.25
        assert backend.output_device == REALTEK
        assert [item.text for item in service.history] == ["can you hear this"]
    finally:
        service.stop()


def test_speech_service_refuses_a_microphone_before_queueing():
    backend = StubSpeechBackend()
    service = SpeechService(backend, preempt_min_priority=70)
    try:
        service.set_output_device(JBL_MIC)
        refused = False
    except Exception as exc:
        refused = True
        assert "voice chat" in str(exc)
    assert refused
    assert backend.output_device is None


def test_pyttsx3_assigns_the_selected_playback_token_and_refuses_a_mic():
    settings = SpeechConfig(
        backend="pyttsx3",
        voice="",
        rate=185,
        volume=0.85,
        output_device=JBL_CHAT,
    )
    backend = Pyttsx3Backend(settings)
    game = _Token(JBL_GAME)
    chat = _Token(JBL_CHAT)
    realtek = _Token(REALTEK)
    monitor = _Token(MONITOR)
    engine = _Engine()
    backend._apply_output_device(
        engine,
        devices=[
            (game.description, game),
            (chat.description, chat),
            (realtek.description, realtek),
            (monitor.description, monitor),
        ],
    )
    assert engine.tts.AudioOutput is chat

    backend.set_volume(0.4)
    assert settings.volume == 0.4
    engine.setProperty("volume", 0.2)
    backend._engine = engine
    backend.set_volume(0.55)
    assert engine.props["volume"] == 0.55

    try:
        backend.set_output_device(JBL_MIC)
        refused = False
    except RuntimeError as exc:
        refused = True
        assert "microphone" in str(exc).lower()
    assert refused
    assert settings.output_device == JBL_CHAT

    mic = _Token(JBL_MIC)
    settings.output_device = "microphone"
    try:
        backend._apply_output_device(engine, devices=[(JBL_MIC, mic), (JBL_CHAT, chat)])
        assigned_mic = False
    except RuntimeError:
        assigned_mic = True
    assert assigned_mic
    assert engine.tts.AudioOutput is chat


def test_substring_that_matches_two_outputs_uses_the_first_and_warns(caplog):
    settings = SpeechConfig(
        backend="pyttsx3",
        voice="",
        rate=185,
        volume=1.0,
        output_device="JBL",
    )
    backend = Pyttsx3Backend(settings)
    engine = _Engine()
    game = _Token(JBL_GAME)
    chat = _Token(JBL_CHAT)
    with caplog.at_level(logging.WARNING):
        backend._apply_output_device(
            engine,
            devices=[(JBL_GAME, game), (JBL_CHAT, chat), (REALTEK, _Token(REALTEK))],
        )
    assert engine.tts.AudioOutput is game
    assert "matches" in caplog.text
    assert JBL_CHAT in caplog.text


def test_sapi_enumeration_is_empty_when_not_on_windows():
    if sys.platform == "win32":
        return
    assert enumerate_sapi_playback_devices() == []
    assert list_output_device_names() == []


class _Token:
    def __init__(self, description: str) -> None:
        self.description = description

    def GetDescription(self) -> str:
        return self.description


class _Engine:
    """Enough of a pyttsx3 engine for device and volume assignment."""

    def __init__(self) -> None:
        self.props: dict[str, float] = {}
        self.tts = SimpleNamespace(AudioOutput=None)
        self.proxy = SimpleNamespace(_driver=SimpleNamespace(_tts=self.tts))

    def setProperty(self, key: str, value: float) -> None:
        self.props[key] = value

    def stop(self) -> None:
        return None
