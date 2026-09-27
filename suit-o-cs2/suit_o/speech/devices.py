"""Playback-device and voice matching for the Windows SAPI backend.

Enumeration of real devices happens on Windows only. Selection itself is a
pure function so tests can cover it without SAPI.
"""

from __future__ import annotations

# Desktop SAPI playback endpoints. This is not the microphone category.
SAPI_AUDIO_OUTPUT = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\AudioOutput"


class DeviceSelectionError(LookupError):
    """The requested playback device or voice is not available."""


def match_voice(voices: list[tuple[str, str]], query: str) -> str | None:
    """Return the voice id whose name contains ``query``.

    An empty query means "use the engine default" and returns None.
    ``voices`` items are ``(display name, voice id)``.
    """

    cleaned = query.strip()
    if not cleaned:
        return None
    needle = cleaned.lower()
    for name, voice_id in voices:
        if needle in name.lower():
            return voice_id
    known = ", ".join(name for name, _voice_id in voices) or "(none)"
    raise DeviceSelectionError(
        f"No installed speech voice matches {query!r}. Installed voices: {known}"
    )


def select_output_token(devices: list[tuple[str, object]], query: str) -> object:
    """Pick a playback token whose description contains ``query``.

    Callers must pass playback devices only (SAPI AudioOutput), never capture
    devices. An empty query is not valid here: blank config means the Windows
    default endpoint, and the caller should not call this function.
    """

    cleaned = query.strip()
    if not cleaned:
        raise DeviceSelectionError("No device query; the Windows default playback device is used.")
    needle = cleaned.lower()
    matches = [(name, token) for name, token in devices if needle in name.lower()]
    if not matches:
        known = ", ".join(name for name, _token in devices) or "(none)"
        raise DeviceSelectionError(
            f"No playback device matches {query!r}. Playback devices: {known}"
        )
    return matches[0][1]
