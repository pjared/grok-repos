"""Save the desktop window's volume, mute, output device, and voice tuning.

The rest of ``config.yaml`` — comments, token, cooldowns — stays as written.
Only the keys the caller passes are replaced. Voice, rate, pitch, pause, and
emphasis are backend-agnostic: a future remote TTS server can read the same
fields.
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
    voice: str | None = None,
    rate: int | None = None,
    pitch: int | None = None,
    pause_ms: int | None = None,
    emphasis: str | None = None,
    backend: str | None = None,
) -> None:
    """Update the passed settings in ``path``. Omitted arguments are left alone.

    Missing keys are inserted. A microphone or virtual-cable name is refused
    and the file is left untouched. Tuning numbers use the same ranges as
    :func:`suit_o.speech.tuning.normalize_tuning`.
    """

    if all(
        value is None
        for value in (
            volume,
            muted,
            output_device,
            voice,
            rate,
            pitch,
            pause_ms,
            emphasis,
            backend,
        )
    ):
        return
    rendered_volume: str | None = None
    rendered_device: str | None = None
    rendered_mute: str | None = None
    rendered_voice: str | None = None
    rendered_rate: str | None = None
    rendered_pitch: str | None = None
    rendered_pause: str | None = None
    rendered_emphasis: str | None = None
    rendered_backend: str | None = None
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
    if backend is not None:
        cleaned_backend = backend.strip().lower()
        if cleaned_backend not in {"pyttsx3", "stub", "clone"}:
            raise ConfigError("speech.backend must be 'pyttsx3', 'stub', or 'clone'")
        rendered_backend = cleaned_backend
    if any(value is not None for value in (voice, rate, pitch, pause_ms, emphasis)):
        (
            rendered_voice,
            rendered_rate,
            rendered_pitch,
            rendered_pause,
            rendered_emphasis,
        ) = _render_tuning(
            voice=voice,
            rate=rate,
            pitch=pitch,
            pause_ms=pause_ms,
            emphasis=emphasis,
        )

    # Read bytes so Windows newlines stay intact. Path.read_text translates them.
    original = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    text = original.replace("\r\n", "\n")
    if rendered_volume is not None:
        text = _replace_yaml_scalar(text, "volume", rendered_volume, parent="speech")
    if rendered_device is not None:
        text = _replace_yaml_scalar(text, "output_device", rendered_device, parent="speech")
    if rendered_backend is not None:
        text = _replace_yaml_scalar(text, "backend", rendered_backend, parent="speech")
    if rendered_voice is not None:
        text = _replace_yaml_scalar(text, "voice", rendered_voice, parent="speech")
    if rendered_rate is not None:
        text = _replace_yaml_scalar(text, "rate", rendered_rate, parent="speech")
    if rendered_pitch is not None:
        text = _replace_yaml_scalar(text, "pitch", rendered_pitch, parent="speech")
    if rendered_pause is not None:
        text = _replace_yaml_scalar(text, "pause_ms", rendered_pause, parent="speech")
    if rendered_emphasis is not None:
        text = _replace_yaml_scalar(text, "emphasis", rendered_emphasis, parent="speech")
    if rendered_mute is not None:
        text = _replace_yaml_scalar(text, "mute", rendered_mute, parent=None)
    if not text.endswith("\n"):
        text += "\n"
    payload = text.replace("\n", newline).encode("utf-8")
    _atomic_write(path, payload)


def _render_tuning(
    *,
    voice: str | None,
    rate: int | None,
    pitch: int | None,
    pause_ms: int | None,
    emphasis: str | None,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Validate provided tuning fields and return YAML scalars.

    A ``None`` argument is not written. Defaults fill the gaps only so one
    field can be checked on its own.
    """

    from suit_o.speech.tuning import (
        DEFAULT_EMPHASIS,
        DEFAULT_PAUSE_MS,
        DEFAULT_PITCH,
        DEFAULT_RATE,
        TuningError,
        VoiceTuning,
        normalize_tuning,
    )

    try:
        checked = normalize_tuning(
            VoiceTuning(
                voice="" if voice is None else voice,
                rate=DEFAULT_RATE if rate is None else rate,
                pitch=DEFAULT_PITCH if pitch is None else pitch,
                pause_ms=DEFAULT_PAUSE_MS if pause_ms is None else pause_ms,
                emphasis=DEFAULT_EMPHASIS if emphasis is None else emphasis,
            )
        )
    except TuningError as exc:
        raise ConfigError(str(exc)) from exc
    return (
        None if voice is None else json.dumps(checked.voice),
        None if rate is None else str(checked.rate),
        None if pitch is None else str(checked.pitch),
        None if pause_ms is None else str(checked.pause_ms),
        None if emphasis is None else json.dumps(checked.emphasis),
    )


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
