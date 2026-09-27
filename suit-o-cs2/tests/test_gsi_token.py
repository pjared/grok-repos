"""A personal GSI token is written once and is not logged."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from suit_o.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT
from suit_o.gsi_token import CFG_NAME, SAMPLE_TOKEN, ensure_personal_token
from suit_o.local_config import (
    local_config_path,
    read_installed_requirements,
    remember_installed_requirements,
    store_personal_settings,
)


def test_personal_token_lands_in_local_config_and_an_outside_cfg(tmp_path: Path, caplog):
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    outside = tmp_path / "csgo" / "cfg" / CFG_NAME
    outside.parent.mkdir(parents=True)
    tracked = PROJECT_ROOT / "gamestate_integration_suito.cfg"
    before = tracked.read_text(encoding="utf-8")
    outside.write_text(before, encoding="utf-8")

    caplog.set_level(logging.DEBUG)
    assert ensure_personal_token(config_path, cfg_files=[tracked, outside]) is True
    local = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))
    token = local["server"]["token"]
    assert token != SAMPLE_TOKEN
    assert len(token) >= 8
    assert token not in caplog.text
    assert SAMPLE_TOKEN not in outside.read_text(encoding="utf-8")
    assert token in outside.read_text(encoding="utf-8")
    assert tracked.read_text(encoding="utf-8") == before

    assert ensure_personal_token(config_path, cfg_files=[outside]) is False
    again = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))
    assert again["server"]["token"] == token


def test_settings_save_keeps_the_token_and_the_install_marker(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    assert ensure_personal_token(config_path, cfg_files=[]) is True
    remember_installed_requirements(config_path, ["requirements-voice.txt"])
    before = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))["server"]["token"]
    store_personal_settings(config_path, volume=0.4)
    saved = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))
    assert saved["server"]["token"] == before
    assert saved["speech"]["volume"] == 0.4
    assert read_installed_requirements(config_path) == {"requirements-voice.txt"}
