"""Volume, mute, output device, and config persistence."""

from __future__ import annotations

from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from suit_o.preferences import clamp_volume, format_volume, save_user_settings
from suit_o.scenario import build_scenario
from suit_o.simulate import post_payload, simulation_config
from suit_o.speech.devices import (
    DeviceSelectionError,
    resolve_output_device,
    selectable_playback_names,
)
from suit_o.speech.stub import StubSpeechBackend

JBL_GAME = "Speakers (JBL Quantum 950X Wireless For Xbox Game)"
JBL_CHAT = "Headset Earphone (JBL Quantum 950X Wireless For Xbox Chat)"
REALTEK = "Realtek Digital Output"
MONITOR = "LG ULTRAGEAR (NVIDIA High Definition Audio)"
JBL_MIC = "Headset Microphone (JBL Quantum 950X Wireless For Xbox Chat)"
PLAYBACK = [JBL_GAME, JBL_CHAT, REALTEK, MONITOR, JBL_MIC]


def test_selectable_names_drop_microphones_and_duplicates():
    names = selectable_playback_names(
        ["", JBL_GAME, JBL_MIC, "CABLE Output", JBL_CHAT, JBL_CHAT, REALTEK, MONITOR, "  "]
    )
    assert names == [JBL_GAME, JBL_CHAT, REALTEK, MONITOR]


def test_resolve_output_device_picks_one_endpoint_and_refuses_a_mic():
    assert resolve_output_device("", PLAYBACK) == ""
    assert resolve_output_device("Windows default", PLAYBACK) == ""
    assert resolve_output_device("chat", PLAYBACK) == JBL_CHAT
    assert resolve_output_device(JBL_GAME, PLAYBACK) == JBL_GAME
    assert resolve_output_device("realtek", PLAYBACK) == REALTEK
    assert resolve_output_device("ultragear", PLAYBACK) == MONITOR

    try:
        resolve_output_device(JBL_MIC, PLAYBACK)
        refused = False
    except ConfigError as exc:
        refused = True
        assert "voice chat" in str(exc)
    assert refused

    try:
        resolve_output_device("JBL", PLAYBACK)
        ambiguous = False
    except DeviceSelectionError as exc:
        ambiguous = True
        assert JBL_GAME in str(exc)
        assert JBL_CHAT in str(exc)
    assert ambiguous

    try:
        resolve_output_device("not a device", PLAYBACK)
        missing = False
    except DeviceSelectionError:
        missing = True
    assert missing


def test_volume_clamp_and_format():
    assert clamp_volume(0.994) == 0.99
    assert clamp_volume(0) == 0.0
    assert clamp_volume(1) == 1.0
    assert format_volume(0.85) == "0.85"
    assert format_volume(1) == "1.0"
    assert format_volume(0.5) == "0.5"
    assert format_volume(0) == "0.0"
    for bad in (1.01, -0.01, True, "loud"):
        try:
            clamp_volume(bad)
            raised = False
        except ConfigError:
            raised = True
        assert raised


def test_save_keeps_comments_and_round_trips(tmp_path: Path):
    path = _copy_config(tmp_path)
    original = path.read_bytes()
    save_user_settings(path, volume=0.85, muted=False, output_device="")
    assert path.read_bytes() == original

    save_user_settings(path, volume=0.4, muted=True, output_device=JBL_CHAT)
    text = path.read_text(encoding="utf-8")
    assert "Words per minute" in text
    assert "sample value" in text or "suito-local-change-me" in text
    assert "Do not set a microphone" in text
    loaded = load_config(path)
    assert loaded.speech.volume == 0.4
    assert loaded.mute is True
    assert loaded.speech.output_device == JBL_CHAT
    assert loaded.speech.rate == 185
    assert loaded.server.port == 3000


def test_save_refuses_a_microphone_and_leaves_the_file(tmp_path: Path):
    path = _copy_config(tmp_path)
    before = path.read_bytes()
    try:
        save_user_settings(path, output_device="CABLE Input")
        refused = False
    except ConfigError as exc:
        refused = True
        assert "voice chat" in str(exc)
    assert refused
    assert path.read_bytes() == before


def test_save_voice_tuning_round_trips_and_preserves_comments(tmp_path: Path):
    path = _copy_config(tmp_path)
    save_user_settings(
        path,
        voice="Microsoft Zira Desktop",
        rate=160,
        pitch=-3,
        pause_ms=120,
        emphasis="strong",
    )
    text = path.read_text(encoding="utf-8")
    assert "Words per minute" in text
    assert "Do not set a microphone" in text
    assert "Pitch offset" in text
    loaded = load_config(path)
    assert loaded.speech.voice == "Microsoft Zira Desktop"
    assert loaded.speech.rate == 160
    assert loaded.speech.pitch == -3
    assert loaded.speech.pause_ms == 120
    assert loaded.speech.emphasis == "strong"
    assert loaded.speech.volume == 0.85
    assert loaded.server.port == 3000

    before = path.read_bytes()
    try:
        save_user_settings(path, pitch=40)
        refused = False
    except ConfigError as exc:
        refused = True
        assert "pitch" in str(exc)
    assert refused
    assert path.read_bytes() == before

    try:
        save_user_settings(path, emphasis="loud")
        refused_emphasis = False
    except ConfigError as exc:
        refused_emphasis = True
        assert "emphasis" in str(exc)
    assert refused_emphasis
    assert path.read_bytes() == before


def test_save_inserts_a_missing_key_and_preserves_crlf(tmp_path: Path):
    path = _copy_config(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith("  volume:")]
    path.write_bytes(("\r\n".join(kept) + "\r\n").encode("utf-8"))
    save_user_settings(path, volume=0.5)
    raw = path.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert b"  volume: 0.5\r\n" in raw
    assert load_config(path).speech.volume == 0.5
    assert b"Do not set a microphone" in raw


def test_app_applies_volume_mute_and_device_and_persists(tmp_path: Path):
    path = _copy_config(tmp_path)
    # Load the real project config so the lines file resolves. Writes go to the copy.
    config = load_config(DEFAULT_CONFIG_PATH)
    backend = StubSpeechBackend()
    app = SuitOApp(
        config,
        backend=backend,
        config_path=path,
        output_devices=lambda: list(PLAYBACK),
    )
    assert app.output_device_names() == [JBL_GAME, JBL_CHAT, REALTEK, MONITOR]
    try:
        app.set_volume(2)
        rejected = False
    except ConfigError:
        rejected = True
    assert rejected
    assert app.config.speech.volume == 0.85

    try:
        app.set_output_device(JBL_MIC)
        refused = False
    except ConfigError as exc:
        refused = True
        assert "voice chat" in str(exc)
    assert refused
    assert app.config.speech.output_device == ""
    assert backend.output_device is None

    app.start()
    try:
        assert app.snapshot().listening
        assert any("Listener up" in item.message for item in app.activity())
        app.set_volume(0.33)
        chosen = app.set_output_device("chat")
        assert chosen == JBL_CHAT
        app.set_muted(True)
        assert app.muted
        assert app.toggle_mute() is False
        app.set_muted(True)
        app.test_voice("Hello from Suit-O")
        assert app.speech.wait_until(
            lambda: backend.volume == 0.33 and backend.output_device == JBL_CHAT,
            2,
        )
        assert app.speech.wait_until(lambda: backend.spoken == ["Hello from Suit-O"], 2)
        assert any(item.message.startswith("test: ") for item in app.activity())
        app.save_preferences()
    finally:
        app.stop()

    saved = load_config(path)
    assert saved.speech.volume == 0.33
    assert saved.speech.output_device == JBL_CHAT
    assert saved.mute is True
    assert "virtual cable" in path.read_text(encoding="utf-8")


def test_payload_age_and_spoken_line_show_up_in_the_log():
    config = simulation_config(DEFAULT_CONFIG_PATH)
    backend = StubSpeechBackend()
    app = SuitOApp(config, backend=backend)
    app.start()
    try:
        assert app.snapshot().seconds_since_payload is None
        host, port = app.server_address
        url = f"http://{host}:{port}/"
        payloads = build_scenario(config.server.token)
        for index, payload in enumerate(payloads[:4], start=1):
            post_payload(url, payload)
            assert app.wait_for_payloads(index, timeout=5)
        shot = app.snapshot()
        assert shot.listening
        assert shot.seconds_since_payload is not None
        assert shot.seconds_since_payload < 5
        assert shot.received >= 4
        assert any(item.message.startswith("warmup:") for item in shot.activity)
    finally:
        app.stop()


def _copy_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    return path
