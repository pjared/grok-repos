"""Save the desktop window's volume, mute, and output device.

The rest of ``config.yaml`` — comments, token, cooldowns — stays as written.
Only the three keys the window edits are replaced.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from suit_o.config import ConfigError, is_disallowed_output_device


def clamp_volume(value: object) -> float:
    """Return ``value`` as a volume in ``0.0`` … ``1.0``, rounded to 0.01."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("speech.volume must be a number from 0.0 to 1.0")
    volume = round(float(value), 2)
    if not 0.0 <= volume <= 1.0:
        raise ConfigError("speech.volume must be between 0.0 and 1.0")
    return volume


def format_volume(volume: float) -> str:
    """YAML scalar for a volume. ``0.85`` stays ``0.85``; ``1`` becomes ``1.0``."""

    text = f"{round(float(volume), 2):.2f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def save_user_settings(
    path: Path,
    *,
    volume: float | None = None,
    muted: bool | None = None,
    output_device: str | None = None,
) -> None:
    """Update volume, mute, and output device in ``path``.

    Missing keys are inserted. A microphone or virtual-cable name is refused
    and the file is left untouched.
    """

    if volume is None and muted is None and output_device is None:
        return
    rendered_volume: str | None = None
    rendered_device: str | None = None
    rendered_mute: str | None = None
    if volume is not None:
        rendered_volume = format_volume(clamp_volume(volume))
    if output_device is not None:
        cleaned = output_device.strip()
        if is_disallowed_output_device(cleaned):
            raise ConfigError(
                "speech.output_device looks like a microphone or a virtual cable "
                "into voice chat. Choose a playback device (headset or speakers), "
                "or leave it blank to use the Windows default playback device."
            )
        rendered_device = json.dumps(cleaned)
    if muted is not None:
        rendered_mute = "true" if muted else "false"

    # Read bytes so Windows newlines stay intact. Path.read_text translates them.
    original = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    text = original.replace("\r\n", "\n")
    if rendered_volume is not None:
        text = _replace_yaml_scalar(text, "volume", rendered_volume, parent="speech")
    if rendered_device is not None:
        text = _replace_yaml_scalar(text, "output_device", rendered_device, parent="speech")
    if rendered_mute is not None:
        text = _replace_yaml_scalar(text, "mute", rendered_mute, parent=None)
    if not text.endswith("\n"):
        text += "\n"
    payload = text.replace("\n", newline).encode("utf-8")
    _atomic_write(path, payload)


def _split_lines(text: str) -> list[str]:
    if text.endswith("\n"):
        text = text[:-1]
    if not text:
        return []
    return text.split("\n")


def _replace_yaml_scalar(text: str, key: str, rendered: str, *, parent: str | None) -> str:
    lines = _split_lines(text)
    if parent is None:
        _replace_root_key(lines, key, rendered)
    else:
        _replace_child_key(lines, parent, key, rendered)
    return "\n".join(lines) + "\n"


def _replace_root_key(lines: list[str], key: str, rendered: str) -> None:
    for index, line in enumerate(lines):
        if _content_indent(line) == 0 and _key_name(line) == key:
            lines[index] = f"{key}: {rendered}"
            return
    lines.append(f"{key}: {rendered}")


def _replace_child_key(lines: list[str], parent: str, key: str, rendered: str) -> None:
    parent_index = None
    for index, line in enumerate(lines):
        if _content_indent(line) == 0 and _key_name(line) == parent:
            parent_index = index
            break
    if parent_index is None:
        raise ConfigError(f"config is missing a {parent}: section")

    child_indent: int | None = None
    found: int | None = None
    section_end = len(lines)
    for index in range(parent_index + 1, len(lines)):
        indent = _content_indent(lines[index])
        if indent is None:
            continue
        if indent == 0:
            section_end = index
            break
        if child_indent is None:
            child_indent = indent
        if indent == child_indent and _key_name(lines[index]) == key and found is None:
            found = index
    if child_indent is None:
        child_indent = 2
    replacement = f"{' ' * child_indent}{key}: {rendered}"
    if found is None:
        lines.insert(section_end, replacement)
    else:
        lines[found] = replacement


def _content_indent(line: str) -> int | None:
    stripped = line.lstrip(" ")
    if not stripped or stripped.startswith("#"):
        return None
    return len(line) - len(stripped)


def _key_name(line: str) -> str | None:
    stripped = line.lstrip(" ")
    if not stripped or stripped.startswith("#") or ":" not in stripped:
        return None
    return stripped.split(":", 1)[0].strip()


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
