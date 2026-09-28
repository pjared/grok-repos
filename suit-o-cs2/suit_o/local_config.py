"""Per-user settings in ``config.local.yaml``, layered over ``config.yaml``.

The tracked file stays at the shared defaults so ``git pull`` can update it.
Volume, the output device, voice tuning, mute, and the lineup overlay are
written here instead. The first launch copies values that already differ
from those defaults — including a headset chosen on the user's PC — into
the local file and puts those keys in ``config.yaml`` back.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import yaml

from suit_o.config import PROJECT_ROOT, ConfigError, read_yaml_mapping

logger = logging.getLogger(__name__)

LOCAL_CONFIG_NAME = "config.local.yaml"
# Tests point this at a throwaway file so they never touch the real overlay.
_project_local_redirect: Path | None = None

SPEECH_DEFAULTS = {
    "backend": "pyttsx3",
    "voice": "",
    "rate": 185,
    "volume": 0.85,
    "pitch": 0,
    "pause_ms": 0,
    "emphasis": "none",
    "output_device": "",
}
LINEUP_DEFAULTS = {
    "enabled": True,
    "width": 320,
    "opacity": 0.92,
    "corner": "top-right",
    "monitor": 0,
    "hotkey_next": "ctrl+shift+right",
    "hotkey_previous": "ctrl+shift+left",
    "hotkey_toggle": "ctrl+shift+h",
    "smokes_only": True,
}
UPDATE_DEFAULTS = {"check_on_launch": False}
_SECTION_DEFAULTS = {
    "speech": SPEECH_DEFAULTS,
    "lineups": LINEUP_DEFAULTS,
    "updates": UPDATE_DEFAULTS,
    "chat": {"ptt_key": "f8"},
}
_HEADER = (
    "# Per-user Suit-O settings. Git ignores this file.\n"
    "# config.yaml stays at the shared defaults so Update can pull.\n\n"
)


def redirect_project_local_config(path: Path | None) -> None:
    """Send reads and writes of the shipped ``config.local.yaml`` to ``path``.

    ``None`` restores the real file next to ``config.yaml``. The test suite
    sets this so a headset saved on a developer machine cannot change results,
    and so a test cannot overwrite that file.
    """

    global _project_local_redirect
    _project_local_redirect = None if path is None else Path(path)


def local_config_path(config_path: Path) -> Path:
    path = Path(config_path).with_name(LOCAL_CONFIG_NAME)
    redirect = _project_local_redirect
    if redirect is not None and _is_project_local(path):
        return redirect
    return path


def _is_project_local(path: Path) -> bool:
    try:
        return path.resolve() == (PROJECT_ROOT / LOCAL_CONFIG_NAME).resolve()
    except OSError:
        return False


def migrate_user_settings(config_path: Path) -> bool:
    """Move GUI settings that differ from the defaults into the local file.

    Returns True when a local file was written. An existing non-empty local
    file is left alone so a later launch cannot clobber it. ``config.yaml``
    keys that were moved are restored to the defaults, comments included.
    """

    config_path = Path(config_path)
    local_path = local_config_path(config_path)
    if _local_has_settings(local_path):
        return False
    raw = read_yaml_mapping(config_path)
    overlay = _diffs_from_defaults(raw)
    if not overlay:
        return False
    payload = _render(overlay)
    temporary = local_path.with_name(local_path.name + ".tmp")
    temporary.write_bytes(payload)
    try:
        _restore_defaults(config_path, raw, overlay)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    os.replace(temporary, local_path)
    logger.info("Moved personal Suit-O settings into %s", local_path.name)
    return True


def store_personal_settings(
    config_path: Path,
    *,
    volume: float | None = None,
    muted: bool | None = None,
    output_device: str | None = None,
    voice: str | None = None,
    rate: int | None = None,
    pitch: int | None = None,
    pause_ms: int | None = None,
    emphasis: str | None = None,
    backend: str | None = None,
    enabled: bool | None = None,
    width: int | None = None,
    opacity: float | None = None,
    corner: str | None = None,
    monitor: int | None = None,
    hotkey_next: str | None = None,
    hotkey_previous: str | None = None,
    hotkey_toggle: str | None = None,
    smokes_only: bool | None = None,
    check_on_launch: bool | None = None,
    menu_greeting: bool | None = None,
    chattiness: str | None = None,
    voice_key: str = "",
    ptt_key: str = "",
    chat_ptt_key: str | None = None,
) -> None:
    """Validate, then keep only values that differ from ``config.yaml``.

    The tracked file is not modified. A value that matches it is removed
    from the local file so a later default in git can show through.
    """

    config_path = Path(config_path)
    user_args = {
        "volume": volume,
        "muted": muted,
        "output_device": output_device,
        "voice": voice,
        "rate": rate,
        "pitch": pitch,
        "pause_ms": pause_ms,
        "emphasis": emphasis,
        "backend": backend,
    }
    lineup_args = {
        "enabled": enabled,
        "width": width,
        "opacity": opacity,
        "corner": corner,
        "monitor": monitor,
        "hotkey_next": hotkey_next,
        "hotkey_previous": hotkey_previous,
        "hotkey_toggle": hotkey_toggle,
        "smokes_only": smokes_only,
    }
    if any(value is not None for value in user_args.values()):
        _validate_user(config_path, user_args)
    if any(value is not None for value in lineup_args.values()):
        _validate_lineups(config_path, lineup_args, voice_key=voice_key, ptt_key=ptt_key)
    if check_on_launch is not None and not isinstance(check_on_launch, bool):
        raise ConfigError("updates.check_on_launch must be true or false")
    if menu_greeting is not None and not isinstance(menu_greeting, bool):
        raise ConfigError("menu_greeting must be true or false")
    if chattiness is not None:
        from suit_o.lines.chattiness import ChattinessError, normalize_chattiness

        try:
            chattiness = normalize_chattiness(chattiness)
        except ChattinessError as exc:
            raise ConfigError(str(exc)) from exc

    base = read_yaml_mapping(config_path)
    local_path = local_config_path(config_path)
    overlay = _read_local(local_path)
    top_level = {}
    if muted is not None:
        top_level["mute"] = muted
    if menu_greeting is not None:
        top_level["menu_greeting"] = menu_greeting
    if chattiness is not None:
        top_level["chattiness"] = chattiness
    _apply_managed(overlay, base, None, top_level)
    _apply_managed(
        overlay,
        base,
        "speech",
        {
            "backend": backend,
            "voice": voice,
            "rate": rate,
            "volume": volume,
            "pitch": pitch,
            "pause_ms": pause_ms,
            "emphasis": emphasis,
            "output_device": output_device,
        },
    )
    _apply_managed(overlay, base, "lineups", lineup_args)
    _apply_managed(
        overlay,
        base,
        "updates",
        {"check_on_launch": check_on_launch} if check_on_launch is not None else {},
    )
    if chat_ptt_key is not None:
        from suit_o.chat.hotkey import normalize_ptt_key

        _apply_managed(overlay, base, "chat", {"ptt_key": normalize_ptt_key(chat_ptt_key)})
    _write_overlay(local_path, overlay)


def _local_has_settings(path: Path) -> bool:
    if not path.is_file():
        return False
    return bool(read_local_document(path))


def _diffs_from_defaults(raw: dict) -> dict:
    overlay: dict = {}
    if "mute" in raw and not _same("mute", raw["mute"], False):
        overlay["mute"] = _coerce("mute", raw["mute"])
    speech = raw.get("speech") if isinstance(raw.get("speech"), dict) else {}
    speech_over = _section_diff(speech, SPEECH_DEFAULTS)
    if speech_over:
        overlay["speech"] = speech_over
    lineups = raw.get("lineups") if isinstance(raw.get("lineups"), dict) else {}
    lineup_over = _section_diff(lineups, LINEUP_DEFAULTS)
    if lineup_over:
        overlay["lineups"] = lineup_over
    updates = raw.get("updates") if isinstance(raw.get("updates"), dict) else {}
    updates_over = _section_diff(updates, UPDATE_DEFAULTS)
    if updates_over:
        overlay["updates"] = updates_over
    return overlay


def _section_diff(raw_section: dict, defaults: dict) -> dict:
    found = {}
    for key, default in defaults.items():
        if key not in raw_section:
            continue
        if _same(key, raw_section[key], default):
            continue
        found[key] = _coerce(key, raw_section[key])
    return found


def _restore_defaults(config_path: Path, raw: dict, overlay: dict) -> None:
    from suit_o.preferences import save_lineup_settings, save_user_settings

    speech = overlay.get("speech") or {}
    user_kwargs = {
        "volume": SPEECH_DEFAULTS["volume"] if "volume" in speech else None,
        "muted": False if "mute" in overlay else None,
        "output_device": SPEECH_DEFAULTS["output_device"] if "output_device" in speech else None,
        "voice": SPEECH_DEFAULTS["voice"] if "voice" in speech else None,
        "rate": SPEECH_DEFAULTS["rate"] if "rate" in speech else None,
        "pitch": SPEECH_DEFAULTS["pitch"] if "pitch" in speech else None,
        "pause_ms": SPEECH_DEFAULTS["pause_ms"] if "pause_ms" in speech else None,
        "emphasis": SPEECH_DEFAULTS["emphasis"] if "emphasis" in speech else None,
        "backend": SPEECH_DEFAULTS["backend"] if "backend" in speech else None,
    }
    if any(value is not None for value in user_kwargs.values()):
        save_user_settings(config_path, **user_kwargs)
    lineups = overlay.get("lineups") or {}
    lineup_kwargs = {
        key: LINEUP_DEFAULTS[key] if key in lineups else None for key in LINEUP_DEFAULTS
    }
    if any(value is not None for value in lineup_kwargs.values()):
        ptt = raw.get("ptt") if isinstance(raw.get("ptt"), dict) else {}
        save_lineup_settings(
            config_path,
            voice_key=str(ptt.get("cs2_voice_key") or ""),
            ptt_key=str(ptt.get("keybind") or ""),
            **lineup_kwargs,
        )
    updates = overlay.get("updates") or {}
    if "check_on_launch" in updates:
        _reset_check_on_launch(config_path)


def _reset_check_on_launch(config_path: Path) -> None:
    """Remove a tracked updates section that only held check_on_launch."""

    text = config_path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    kept: list[str] = []
    in_updates = False
    for line in lines:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped) if stripped else None
        if stripped and not stripped.startswith("#") and indent == 0 and stripped.startswith("updates:"):
            in_updates = True
            continue
        if in_updates:
            if stripped and not stripped.startswith("#") and indent == 0:
                in_updates = False
            else:
                continue
        kept.append(line)
    payload = "\n".join(kept)
    if not payload.endswith("\n"):
        payload += "\n"
    _atomic_write(config_path, payload.replace("\n", newline).encode("utf-8"))


def _validate_user(config_path: Path, values: dict) -> None:
    import tempfile

    from suit_o.preferences import save_user_settings

    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "config.yaml"
        copy.write_bytes(config_path.read_bytes())
        save_user_settings(
            copy,
            volume=values["volume"],
            muted=values["muted"],
            output_device=values["output_device"],
            voice=values["voice"],
            rate=values["rate"],
            pitch=values["pitch"],
            pause_ms=values["pause_ms"],
            emphasis=values["emphasis"],
            backend=values["backend"],
        )


def _validate_lineups(config_path: Path, values: dict, *, voice_key: str, ptt_key: str) -> None:
    import tempfile

    from suit_o.preferences import save_lineup_settings

    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "config.yaml"
        copy.write_bytes(config_path.read_bytes())
        save_lineup_settings(copy, voice_key=voice_key, ptt_key=ptt_key, **values)


def _apply_managed(overlay: dict, base: dict, section: str | None, values: dict) -> None:
    if not any(value is not None for value in values.values()):
        return
    if section is None:
        target = overlay
        base_section = base
        defaults = {"mute": False, "menu_greeting": True, "chattiness": "normal"}
    else:
        current = overlay.get(section)
        target = current if isinstance(current, dict) else {}
        base_raw = base.get(section)
        base_section = base_raw if isinstance(base_raw, dict) else {}
        defaults = _SECTION_DEFAULTS[section]
    for key, value in values.items():
        if value is None:
            continue
        coerced = _coerce(key, value)
        baseline = base_section[key] if key in base_section else defaults[key]
        if _same(key, coerced, baseline):
            target.pop(key, None)
        else:
            target[key] = coerced
    if section is not None:
        if target:
            overlay[section] = target
        else:
            overlay.pop(section, None)


def read_local_document(path: Path) -> dict:
    """Read ``config.local.yaml``. A file that does not parse is copied aside and left in place."""

    if not path.is_file():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        backup = _backup_unreadable(path)
        raise ConfigError(_unreadable_message(path, backup)) from exc
    except OSError:
        raise
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        backup = _backup_unreadable(path)
        raise ConfigError(_unreadable_message(path, backup))
    return dict(loaded)


def _unreadable_message(path: Path, backup: Path) -> str:
    return (
        f"{path.name} could not be read, so Suit-O left it unchanged and copied it to {backup.name}."
    )


def _backup_unreadable(path: Path) -> Path:
    raw = path.read_bytes()
    for existing in path.parent.glob(f"{path.name}.*.bak"):
        try:
            if existing.is_file() and existing.read_bytes() == raw:
                return existing
        except OSError:
            continue
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.{stamp}.bak")
    counter = 2
    while dest.exists():
        dest = path.with_name(f"{path.name}.{stamp}-{counter}.bak")
        counter += 1
    dest.write_bytes(raw)
    return dest


def _read_local(path: Path) -> dict:
    return read_local_document(path)


def _write_overlay(path: Path, overlay: dict) -> None:
    if not overlay:
        if path.is_file():
            path.unlink()
        return
    _atomic_write(path, _render(overlay))


def _render(overlay: dict) -> bytes:
    body = yaml.safe_dump(overlay, sort_keys=False, default_flow_style=False)
    return (_HEADER + body).encode("utf-8")


def _same(key: str, current: object, default: object) -> bool:
    try:
        return _coerce(key, current) == _coerce(key, default)
    except ConfigError:
        return False


def _coerce(key: str, value: object) -> object:
    if key in {"mute", "enabled", "check_on_launch", "smokes_only", "menu_greeting"}:
        if isinstance(value, bool):
            return value
        raise ConfigError(f"{key} must be true or false")
    if key in {"rate", "pitch", "pause_ms", "width", "monitor"}:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{key} must be an integer")
        return value
    if key in {"volume", "opacity"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{key} must be a number")
        return round(float(value), 2)
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    text = value.strip()
    if key in {"backend", "corner"} or key.startswith("hotkey_"):
        return "".join(text.lower().split()) if key.startswith("hotkey_") else text.lower()
    return text


def read_installed_requirements(config_path: Path) -> set[str]:
    """Optional requirement files this PC has already installed."""

    try:
        raw = read_local_document(local_config_path(config_path)).get("installed_requirements")
    except ConfigError:
        return set()
    if not isinstance(raw, list):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def remember_installed_requirements(config_path: Path, names: list[str]) -> str:
    """Record optional requirement files so Update can reinstall only those.

    Returns a warning when the local file could not be read. The file is not
    written when the list is already recorded or when it cannot be parsed.
    """

    fresh = {name.strip() for name in names if name.strip()}
    if not fresh:
        return ""
    path = local_config_path(config_path)
    try:
        data = read_local_document(path)
    except ConfigError as exc:
        logger.warning("%s", exc)
        return str(exc)
    current = data.get("installed_requirements")
    kept = [str(item) for item in current] if isinstance(current, list) else []
    changed = False
    for name in sorted(fresh):
        if name not in kept:
            kept.append(name)
            changed = True
    if not changed:
        return ""
    data["installed_requirements"] = kept
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, yaml.safe_dump(data, sort_keys=False).encode("utf-8"))
    return ""


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.is_file():
        try:
            if path.read_bytes() == payload:
                return
        except OSError:
            pass
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
