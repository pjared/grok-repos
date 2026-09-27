"""Speech queue preemption and playback-device selection."""

from __future__ import annotations

import threading

from suit_o.config import SpeechConfig, is_disallowed_output_device
from suit_o.models import Utterance
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.devices import DeviceSelectionError, match_voice, select_output_token
from suit_o.speech.factory import create_backend
from suit_o.speech.remote import RemoteTtsBackend
from suit_o.speech.service import SpeechService


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
