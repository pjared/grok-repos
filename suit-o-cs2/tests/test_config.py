"""Config validation, the shipped files, and the GSI cfg contract."""

from __future__ import annotations

from pathlib import Path

import yaml

from suit_o.config import (
    DEFAULT_CONFIG_PATH,
    PROJECT_ROOT,
    ConfigError,
    is_disallowed_output_device,
    load_config,
    normalize_keybind,
    parse_config,
)
from suit_o.models import EventType


def _raw() -> dict:
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def test_shipped_config_loads_and_warns_about_the_sample_token():
    config = load_config(DEFAULT_CONFIG_PATH)
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 3000
    assert config.speech.backend == "pyttsx3"
    assert config.speech.output_device == ""
    assert config.ptt.keybind == ""
    assert config.ptt.cs2_voice_key == "v"
    assert config.lines_path.is_file()
    assert set(config.priority) == {event.value for event in EventType}
    assert any("sample value" in warning for warning in config.warnings)


def test_gsi_cfg_points_at_the_local_endpoint_and_token():
    text = (PROJECT_ROOT / "gamestate_integration_suito.cfg").read_text(encoding="utf-8")
    config = load_config(DEFAULT_CONFIG_PATH)
    assert "http://127.0.0.1:3000" in text
    assert config.server.token in text
    for key in (
        "provider",
        "map",
        "round",
        "player_id",
        "player_state",
        "player_match_stats",
        "player_weapons",
        "bomb",
    ):
        assert f'"{key}"' in text
    assert "allplayers" not in text


def test_ptt_must_differ_from_the_cs2_voice_key():
    raw = _raw()
    raw["ptt"]["keybind"] = "V"
    raw["ptt"]["cs2_voice_key"] = "v"
    try:
        parse_config(raw)
        raised = False
    except ConfigError as exc:
        raised = True
        assert "voice" in str(exc).lower()
    assert raised

    raw["ptt"]["keybind"] = "left alt"
    raw["ptt"]["cs2_voice_key"] = "leftalt"
    try:
        parse_config(raw)
        raised_spaces = False
    except ConfigError:
        raised_spaces = True
    assert raised_spaces
    assert normalize_keybind("left alt") == normalize_keybind("leftalt")


def test_rejects_public_bind_short_token_bad_device_and_remote_backend():
    raw = _raw()
    raw["server"]["host"] = "0.0.0.0"
    try:
        parse_config(raw)
        raised_host = False
    except ConfigError as exc:
        raised_host = True
        assert "127.0.0.1" in str(exc)
    assert raised_host

    raw = _raw()
    raw["server"]["host"] = "localhost"
    assert parse_config(raw).server.host == "127.0.0.1"

    raw = _raw()
    raw["server"]["token"] = "short"
    try:
        parse_config(raw)
        raised_token = False
    except ConfigError:
        raised_token = True
    assert raised_token

    raw = _raw()
    raw["speech"]["output_device"] = "CABLE Input"
    try:
        parse_config(raw)
        raised_device = False
    except ConfigError as exc:
        raised_device = True
        assert "voice chat" in str(exc)
    assert raised_device
    assert is_disallowed_output_device("CABLE Input")

    raw = _raw()
    raw["speech"]["backend"] = "remote"
    try:
        parse_config(raw)
        raised_remote = False
    except ConfigError as exc:
        raised_remote = True
        assert "not implemented" in str(exc)
    assert raised_remote

    raw = _raw()
    raw["speech"]["volume"] = 2
    try:
        parse_config(raw)
        raised_volume = False
    except ConfigError:
        raised_volume = True
    assert raised_volume


def test_remote_url_is_ignored(tmp_path: Path):
    raw = _raw()
    raw["speech"]["remote"]["url"] = "http://192.168.1.50:5000/speak"
    config = parse_config(raw, config_path=tmp_path / "config.yaml")
    assert config.speech.backend == "pyttsx3"
    assert any("ignored" in warning for warning in config.warnings)
