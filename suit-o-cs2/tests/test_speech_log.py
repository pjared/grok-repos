"""In-window speech log: spoken lines, silence reasons, and a redacted token."""

from __future__ import annotations

import time
import urllib.error
from pathlib import Path

from suit_o.app import SuitOApp, _LOG_LIMIT
from suit_o.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT, load_config
from suit_o.gsi.payloads import make_payload
from suit_o.gui.status import format_activity
from suit_o.lines.provider import YamlLineProvider
from suit_o.models import EventType, GameEvent, Utterance
from suit_o.simulate import post_payload, simulation_config
from suit_o.speech.stub import StubSpeechBackend


def test_window_log_shows_spoken_lines_and_skip_reasons():
    moments = iter([0.0, 3.0, 4.0, 4.0])
    app = SuitOApp(
        load_config(DEFAULT_CONFIG_PATH),
        backend=StubSpeechBackend(),
        config_path=DEFAULT_CONFIG_PATH,
        clock=lambda: next(moments),
    )
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=0, kills=0))
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=1, kills=1))
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=2, kills=2))
    app.set_muted(True)
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=2, kills=2, health=10))
    app._on_speech_dropped(Utterance(event_type="kill", text="Nice.", priority=36))

    entries = app.activity()
    messages = [item.message for item in entries]
    assert any(message.endswith("skipped (cooldown)") for message in messages)
    assert any(message.endswith("skipped (muted)") for message in messages)
    assert any(message == "kill: skipped (queue full)" for message in messages)
    spoken = [message for message in messages if message.startswith("kill: ") and "skipped" not in message]
    assert spoken
    painted = format_activity(entries[-1])
    assert painted.endswith("  " + entries[-1].message)
    assert painted.startswith(time.strftime("%H:%M:%S", time.localtime(entries[-1].at)))


def test_silence_reasons_include_no_line_and_lower_priority():
    chooser = YamlLineProvider(
        {"kill": ["Nice."]},
        default_cooldown=0,
        min_interval=10,
        preempt_min_priority=70,
    )
    kill = GameEvent(EventType.KILL, 36, {})
    death = GameEvent(EventType.DEATH, 36, {})
    assert chooser.decide(kill, 0).status == "spoken"
    assert chooser.decide(death, 1).status == "no matching line"
    assert chooser.decide(kill, 2).status == "lower priority"


def test_window_log_keeps_a_bounded_number_of_entries():
    app = SuitOApp(load_config(DEFAULT_CONFIG_PATH), backend=StubSpeechBackend())
    total = _LOG_LIMIT + 40
    for index in range(total):
        app.note(f"line {index}")
    entries = app.activity()
    assert len(entries) == _LOG_LIMIT
    assert entries[0].message == f"line {total - _LOG_LIMIT}"
    assert entries[-1].message == f"line {total - 1}"


def test_window_log_redacts_the_auth_token():
    app = SuitOApp(load_config(DEFAULT_CONFIG_PATH), backend=StubSpeechBackend())
    token = app.config.server.token
    app.note(f"see {token} here")
    messages = [item.message for item in app.activity()]
    assert any("[redacted]" in message for message in messages)
    assert all(token not in message for message in messages)


def test_rejected_payload_stays_in_memory_without_the_token(tmp_path: Path):
    config = simulation_config(DEFAULT_CONFIG_PATH)
    real = config.server.token
    wrong = "wrong-token-value-77"
    app = SuitOApp(
        config,
        backend=StubSpeechBackend(),
        line_provider=YamlLineProvider({}),
    )
    app.start()
    try:
        host, port = app.server_address
        url = f"http://{host}:{port}/"
        bad = make_payload(token=wrong, map_name="de_mirage", round_number=2)
        bad["player"]["name"] = real
        try:
            post_payload(url, bad)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
            exc.read()
        else:
            raise AssertionError("a bad token was accepted")
        post_payload(url, make_payload(token=real, map_name="de_mirage", round_number=2, round_kills=0))
        post_payload(
            url,
            make_payload(token=real, map_name="de_mirage", round_number=2, round_kills=1, kills=1),
        )
        deadline = time.time() + 2
        while time.time() < deadline:
            messages = [item.message for item in app.activity()]
            if any(message.endswith("skipped (no matching line)") for message in messages):
                break
            time.sleep(0.02)
    finally:
        app.stop()

    messages = [item.message for item in app.activity()]
    assert "gsi: rejected (bad token)" in messages
    assert any(message.endswith("skipped (no matching line)") for message in messages)
    assert all(real not in message and wrong not in message for message in messages)
    assert not (tmp_path / "logs").exists()
    assert not list(tmp_path.glob("speech-*.jsonl"))
    assert not (PROJECT_ROOT / "logs").exists()
    assert not list(PROJECT_ROOT.glob("speech-*.jsonl"))
