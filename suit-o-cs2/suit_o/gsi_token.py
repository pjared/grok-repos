"""A personal GSI token, written once. The sample in git stays shared."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import yaml

from suit_o.config import PROJECT_ROOT
from suit_o.local_config import local_config_path

SAMPLE_TOKEN = "suito-local-change-me"
CFG_NAME = "gamestate_integration_suito.cfg"


def ensure_personal_token(config_path: Path, cfg_files: list[Path] | None = None) -> bool:
    """Put a random token in config.local.yaml and in an existing CS2 cfg.

    Returns True when a new token was created. The token is not logged.
    The tracked cfg in the repository is left alone.
    """

    config_path = Path(config_path)
    local_path = local_config_path(config_path)
    data = _read_yaml(local_path)
    current = _server_token(data)
    if current and current != SAMPLE_TOKEN:
        return False
    token = secrets.token_urlsafe(24)
    server = data.get("server")
    if not isinstance(server, dict):
        server = {}
    server = dict(server)
    server["token"] = token
    data["server"] = server
    _write_yaml(local_path, data)
    for cfg in cfg_files if cfg_files is not None else discover_cfg_files():
        if _inside_project(cfg):
            continue
        _replace_sample(cfg, token)
    return True


def discover_cfg_files() -> list[Path]:
    """CS2 cfg copies that still live outside this repository."""

    found: list[Path] = []
    for folder in _cfg_directories():
        candidate = folder / CFG_NAME
        try:
            if not candidate.is_file():
                continue
            if _inside_project(candidate):
                continue
        except OSError:
            continue
        found.append(candidate)
    return found


def _cfg_directories() -> list[Path]:
    override = os.environ.get("SUIT_O_CS2_CFG", "").strip()
    home = Path.home()
    candidates = [
        Path(override) if override else None,
        home / "Library/Application Support/Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg",
        Path("C:/Program Files (x86)/Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg"),
        Path("C:/Program Files/Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg"),
    ]
    folders: list[Path] = []
    for candidate in candidates:
        if candidate is None or not str(candidate):
            continue
        try:
            if candidate.is_dir():
                folders.append(candidate)
        except OSError:
            continue
    return folders


def _inside_project(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return False
    return True


def _server_token(data: dict) -> str:
    server = data.get("server")
    if not isinstance(server, dict):
        return ""
    return str(server.get("token") or "").strip()


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    os.replace(temporary, path)


def _replace_sample(path: Path, token: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    if SAMPLE_TOKEN not in text:
        return
    path.write_text(text.replace(SAMPLE_TOKEN, token), encoding="utf-8")
