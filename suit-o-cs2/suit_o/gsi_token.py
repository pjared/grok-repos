"""A personal GSI token, written once. The sample in git stays shared."""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

import yaml

from suit_o.config import PROJECT_ROOT, ConfigError
from suit_o.local_config import local_config_path, read_local_document

SAMPLE_TOKEN = "suito-local-change-me"
CFG_NAME = "gamestate_integration_suito.cfg"
MISSING_CFG_WARNING = (
    "Suit-O could not find CS2's gamestate_integration_suito.cfg, so it did not change the GSI key. "
    "Copy that file into CS2's cfg folder, then start Suit-O again."
)
UNWRITTEN_CFG_WARNING = (
    "Suit-O found CS2's gamestate config but could not update it, so it did not change the GSI key."
)
_CS2_CFG = Path("steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg")
_TOKEN_LINE = re.compile(r'"token"\s+"([^"]*)"')
_VDF_PATH = re.compile(r'"path"\s+"((?:\\.|[^"])*)"', re.IGNORECASE)


@dataclass(frozen=True)
class TokenSetup:
    created: bool
    warning: str = ""


def ensure_personal_token(config_path: Path, cfg_files: list[Path] | None = None) -> TokenSetup:
    """Keep an existing GSI key, or write a new one only after the CS2 cfg is updated.

    A new token is not saved when the cfg file cannot be found or written.
    The token is not logged. The tracked cfg in the repository is left alone.
    """

    config_path = Path(config_path)
    local_path = local_config_path(config_path)
    try:
        data = read_local_document(local_path)
    except ConfigError as exc:
        return TokenSetup(False, str(exc))
    current = _server_token(data)
    cfgs = _outside(cfg_files if cfg_files is not None else discover_cfg_files())
    if current and current != SAMPLE_TOKEN:
        if not cfgs:
            return TokenSetup(False, MISSING_CFG_WARNING)
        return TokenSetup(False, "")
    existing = _existing_cfg_token(cfgs)
    if existing:
        _remember(local_path, data, existing)
        for cfg in cfgs:
            _replace_sample(cfg, existing)
        return TokenSetup(False, "")
    if not cfgs:
        return TokenSetup(False, MISSING_CFG_WARNING)
    token = secrets.token_urlsafe(24)
    written = False
    for cfg in cfgs:
        written = _replace_sample(cfg, token) or written
    if not written:
        return TokenSetup(False, UNWRITTEN_CFG_WARNING)
    _remember(local_path, data, token)
    return TokenSetup(True, "")


def discover_cfg_files(manifests: list[Path] | None = None) -> list[Path]:
    """CS2 cfg copies that still live outside this repository."""

    found: list[Path] = []
    for folder in _cfg_directories(manifests):
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


def _cfg_directories(manifests: list[Path] | None = None) -> list[Path]:
    folders: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path | None) -> None:
        if candidate is None or not str(candidate):
            return
        try:
            if not candidate.is_dir():
                return
            resolved = candidate.resolve()
        except OSError:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        folders.append(candidate)

    override = os.environ.get("SUIT_O_CS2_CFG", "").strip()
    if override:
        add(Path(override))
    for library in _library_roots(manifests):
        add(library / _CS2_CFG)
    if manifests is None:
        home = Path.home()
        for candidate in (
            home / "Library/Application Support/Steam" / _CS2_CFG,
            Path("C:/Program Files (x86)/Steam") / _CS2_CFG,
            Path("C:/Program Files/Steam") / _CS2_CFG,
        ):
            add(candidate)
    return folders


def _library_roots(manifests: list[Path] | None) -> list[Path]:
    roots: list[Path] = []
    for manifest in _default_manifests() if manifests is None else manifests:
        roots.extend(_paths_in_manifest(manifest))
    return roots


def _default_manifests() -> list[Path]:
    home = Path.home()
    names = (
        home / "Library/Application Support/Steam/steamapps/libraryfolders.vdf",
        home / "Library/Application Support/Steam/config/libraryfolders.vdf",
        home / ".steam/steam/steamapps/libraryfolders.vdf",
        home / ".steam/steam/config/libraryfolders.vdf",
        home / ".local/share/Steam/steamapps/libraryfolders.vdf",
        home / ".local/share/Steam/config/libraryfolders.vdf",
        Path("C:/Program Files (x86)/Steam/steamapps/libraryfolders.vdf"),
        Path("C:/Program Files (x86)/Steam/config/libraryfolders.vdf"),
        Path("C:/Program Files/Steam/steamapps/libraryfolders.vdf"),
        Path("C:/Program Files/Steam/config/libraryfolders.vdf"),
    )
    return [path for path in names if path.is_file()]


def _paths_in_manifest(path: Path) -> list[Path]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    roots: list[Path] = []
    for match in _VDF_PATH.finditer(text):
        raw = match.group(1).replace("\\\\", "\\")
        if raw:
            roots.append(Path(raw))
    return roots


def _outside(paths: list[Path]) -> list[Path]:
    return [path for path in paths if not _inside_project(path)]


def _existing_cfg_token(paths: list[Path]) -> str:
    for path in paths:
        token = _cfg_token(path)
        if token and token != SAMPLE_TOKEN:
            return token
    return ""


def _cfg_token(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = _TOKEN_LINE.search(text)
    if match is None:
        return ""
    return match.group(1).strip()


def _remember(path: Path, data: dict, token: str) -> None:
    server = data.get("server")
    if not isinstance(server, dict):
        server = {}
    server = dict(server)
    server["token"] = token
    data["server"] = server
    _write_yaml(path, data)


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


def _write_yaml(path: Path, data: dict) -> None:
    payload = yaml.safe_dump(data, sort_keys=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == payload:
                return
        except OSError:
            pass
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _replace_sample(path: Path, token: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if SAMPLE_TOKEN not in text:
        return False
    try:
        path.write_text(text.replace(SAMPLE_TOKEN, token), encoding="utf-8")
    except OSError:
        return False
    return True
