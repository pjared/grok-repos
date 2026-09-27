"""Playback-device and voice matching for the Windows SAPI backend.

Enumeration of real devices happens on Windows only. Selection itself is a
pure function so tests can cover it without SAPI. Capture devices are never
listed: the category below is AudioOutput, and names that look like a
microphone or a virtual cable are dropped before a caller can choose them.
"""

from __future__ import annotations

import logging
import sys

from suit_o.config import ConfigError, is_disallowed_output_device

logger = logging.getLogger(__name__)

# Desktop SAPI playback endpoints. This is not the microphone category.
SAPI_AUDIO_OUTPUT = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\AudioOutput"

# Label used by the desktop window. Stored in config as an empty string.
WINDOWS_DEFAULT_LABEL = "Windows default"

_DEFAULT_QUERIES = frozenset(
    {
        "",
        "default",
        "windows default",
        "windows default playback device",
    }
)


class DeviceSelectionError(LookupError):
    """The requested playback device or voice is not available."""


def is_default_output_query(query: str) -> bool:
    """True when ``query`` means "use the Windows default playback device"."""

    return query.strip().lower() in _DEFAULT_QUERIES


def selectable_playback_names(names: list[str]) -> list[str]:
    """Playback names a person may choose, in the original order.

    Blank names, duplicates, microphones, and virtual-cable names are omitted.
    """

    chosen: list[str] = []
    for name in names:
        cleaned = name.strip()
        if not cleaned or is_disallowed_output_device(cleaned):
            continue
        if cleaned not in chosen:
            chosen.append(cleaned)
    return chosen


def matching_playback_devices(
    devices: list[tuple[str, object]], query: str
) -> list[tuple[str, object]]:
    """Playback entries whose name matches ``query``.

    An exact case-insensitive name wins over a substring, so a saved full
    name does not stick to a shorter device that happens to contain it.
    An empty query is not valid here: blank config means the Windows default
    endpoint, and the caller should not ask for a token.
    """

    cleaned = query.strip()
    if not cleaned:
        raise DeviceSelectionError(
            "No device query; the Windows default playback device is used."
        )
    needle = cleaned.lower()
    exact = [(name, token) for name, token in devices if name.lower() == needle]
    if exact:
        return exact
    return [(name, token) for name, token in devices if needle in name.lower()]


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
    """Pick a playback token whose description matches ``query``.

    Callers must pass playback devices only (SAPI AudioOutput), never capture
    devices. An empty query is not valid here: blank config means the Windows
    default endpoint, and the caller should not call this function.
    """

    matches = matching_playback_devices(devices, query)
    if not matches:
        known = ", ".join(name for name, _token in devices) or "(none)"
        raise DeviceSelectionError(
            f"No playback device matches {query!r}. Playback devices: {known}"
        )
    return matches[0][1]


def resolve_output_device(query: str, available: list[str] | None = None) -> str:
    """Return the device name to store and to hand to the speech backend.

    ``""`` means the Windows default playback device. A non-empty result is
    the matched device's full name when ``available`` is provided, so the
    next launch selects the same endpoint. Microphone and virtual-cable
    names are refused. When ``available`` is None, enumeration did not run
    and any allowed name is kept as written.
    """

    if is_default_output_query(query):
        return ""
    cleaned = query.strip()
    if is_disallowed_output_device(cleaned):
        raise ConfigError(
            "speech.output_device looks like a microphone or a virtual cable "
            "into voice chat. Choose a playback device (headset or speakers), "
            "or leave it blank to use the Windows default playback device."
        )
    if available is None:
        return cleaned
    names = selectable_playback_names(available)
    exact = [name for name in names if name.lower() == cleaned.lower()]
    if exact:
        return exact[0]
    partial = [name for name in names if cleaned.lower() in name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise DeviceSelectionError(
            f"Playback device {query!r} matches more than one output: "
            + ", ".join(partial)
            + ". Choose the full playback name."
        )
    known = ", ".join(names) or "(none)"
    raise DeviceSelectionError(
        f"No playback device matches {query!r}. Playback devices: {known}"
    )


def list_output_device_names() -> list[str]:
    """Names of SAPI playback devices on this machine.

    Empty when not on Windows or when SAPI cannot be asked. Microphones are
    not included.
    """

    try:
        pairs = enumerate_sapi_playback_devices()
    except Exception:
        logger.warning("Could not list SAPI playback devices", exc_info=True)
        return []
    return selectable_playback_names([name for name, _token in pairs])


def enumerate_sapi_playback_devices() -> list[tuple[str, object]]:
    """List SAPI playback endpoints. Never enumerates AudioInput.

    Tokens whose description looks like a microphone or a virtual cable are
    omitted so they cannot be selected later.
    """

    if sys.platform != "win32":
        return []
    try:
        import comtypes.client
    except ImportError:
        logger.warning("comtypes is not installed; playback devices cannot be listed.")
        return []
    try:
        category = comtypes.client.CreateObject("SAPI.SpObjectTokenCategory")
        category.SetId(SAPI_AUDIO_OUTPUT, False)
        tokens = category.EnumerateTokens()
    except Exception:
        logger.warning("Could not list SAPI playback devices", exc_info=True)
        return []
    devices: list[tuple[str, object]] = []
    for token in tokens:
        try:
            name = str(token.GetDescription())
        except Exception:
            logger.debug("Skipping a SAPI token with no description", exc_info=True)
            continue
        if is_disallowed_output_device(name):
            logger.warning(
                "Ignoring playback device %r; it looks like a microphone or a virtual cable.",
                name,
            )
            continue
        devices.append((name, token))
    return devices
