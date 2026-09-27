"""A personal GSI token is written once and is not logged."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from suit_o.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT
from suit_o.gsi_token import CFG_NAME, SAMPLE_TOKEN, discover_cfg_files, ensure_personal_token
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
    created = ensure_personal_token(config_path, cfg_files=[tracked, outside])
    assert created.created is True
    assert created.warning == ""
    local = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))
    token = local["server"]["token"]
    assert token != SAMPLE_TOKEN
    assert len(token) >= 8
    assert token not in caplog.text
    assert SAMPLE_TOKEN not in outside.read_text(encoding="utf-8")
    assert token in outside.read_text(encoding="utf-8")
    assert tracked.read_text(encoding="utf-8") == before

    assert ensure_personal_token(config_path, cfg_files=[outside]).created is False
    again = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))
    assert again["server"]["token"] == token


def test_settings_save_keeps_the_token_and_the_install_marker(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    outside = tmp_path / "csgo" / "cfg" / CFG_NAME
    outside.parent.mkdir(parents=True)
    outside.write_text((PROJECT_ROOT / "gamestate_integration_suito.cfg").read_text(encoding="utf-8"), encoding="utf-8")
    assert ensure_personal_token(config_path, cfg_files=[outside]).created is True
    remember_installed_requirements(config_path, ["requirements-voice.txt"])
    before = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))["server"]["token"]
    store_personal_settings(config_path, volume=0.4)
    saved = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))
    assert saved["server"]["token"] == before
    assert saved["speech"]["volume"] == 0.4
    assert read_installed_requirements(config_path) == {"requirements-voice.txt"}


def test_existing_cfg_key_is_kept_and_a_missing_cfg_is_not_replaced(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    outside = tmp_path / "csgo" / "cfg" / CFG_NAME
    outside.parent.mkdir(parents=True)
    text = (PROJECT_ROOT / "gamestate_integration_suito.cfg").read_text(encoding="utf-8")
    outside.write_text(text.replace(SAMPLE_TOKEN, "already-mine-token"), encoding="utf-8")

    kept = ensure_personal_token(config_path, cfg_files=[outside])
    assert kept.created is False
    assert kept.warning == ""
    local = yaml.safe_load(local_config_path(config_path).read_text(encoding="utf-8"))
    assert local["server"]["token"] == "already-mine-token"
    assert outside.read_text(encoding="utf-8").count("already-mine-token") == 1

    other_dir = tmp_path / "missing"
    other_dir.mkdir()
    other = other_dir / "config.yaml"
    other.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    missing = ensure_personal_token(other, cfg_files=[])
    assert missing.created is False
    assert missing.warning
    assert "could not find" in missing.warning.lower()
    assert not local_config_path(other).exists()

    blocked = tmp_path / "not-a-file.cfg"
    blocked.mkdir()
    third_dir = tmp_path / "blocked"
    third_dir.mkdir()
    third = third_dir / "config.yaml"
    third.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    refused = ensure_personal_token(third, cfg_files=[blocked])
    assert refused.created is False
    assert "could not update" in refused.warning.lower()
    assert not local_config_path(third).exists()


def test_a_steam_library_on_another_drive_is_found(tmp_path: Path):
    library = tmp_path / "SteamLibrary"
    cfg = library / "steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg"
    cfg.mkdir(parents=True)
    cfg_file = cfg / CFG_NAME
    cfg_file.write_text(
        (PROJECT_ROOT / "gamestate_integration_suito.cfg").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = tmp_path / "libraryfolders.vdf"
    manifest.write_text(
        '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"'
        + str(library).replace("\\", "\\\\")
        + '"\n\t}\n}\n',
        encoding="utf-8",
    )
    found = discover_cfg_files(manifests=[manifest])
    assert cfg_file in found or cfg_file.resolve() in {path.resolve() for path in found}
