"""Voice tuning that any speech backend can share.

The fields are not SAPI-specific. Rate is words per minute, volume is 0 to 1,
pitch is a signed offset, pause is milliseconds of silence before a line, and
emphasis is none, mild, or strong. The pyttsx3 backend maps pitch, pause, and
emphasis onto SAPI XML for each utterance. A future remote or cloned-voice
backend can map the same fields onto its own API.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_RATE = 185
DEFAULT_VOLUME = 0.85
DEFAULT_PITCH = 0
DEFAULT_PAUSE_MS = 0
DEFAULT_EMPHASIS = "none"
DEFAULT_VOICE = ""

RATE_MIN = 80
RATE_MAX = 400
PITCH_MIN = -10
PITCH_MAX = 10
PAUSE_MIN = 0
PAUSE_MAX = 1000

EMPHASIS_LEVELS = ("none", "mild", "strong")
EMPHASIS_LABELS = {"none": "None", "mild": "Mild", "strong": "Strong"}

# Shown in the voice picker. Stored in config as an empty string.
ENGINE_DEFAULT_VOICE = "Engine default"

# Extra pitch added only while rendering strong emphasis, still clamped.
_STRONG_EMPHASIS_PITCH = 3

_DEFAULT_VOICE_QUERIES = frozenset(
    {
        "",
        "default",
        "engine default",
        "windows default",
    }
)

# SAPI voice tokens. This is not an audio input category.
SAPI_VOICES = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices"

# SVSFlagsAsync, so stop() can interrupt. SVSFIsXML parses pitch and silence.
SAPI_SPEAK_ASYNC = 1
SAPI_SPEAK_XML = 8

DEFAULT_PREVIEW_LINE = (
    "Helpful tip: this is Suit-O, checking the voice. "
    "Detective mode says the headset is a headset."
)


class TuningError(ValueError):
    """A voice setting is outside the range every backend is asked to honor."""


@dataclass(frozen=True)
class VoiceTuning:
    """One snapshot of the knobs on the voice panel."""

    voice: str = DEFAULT_VOICE
    rate: int = DEFAULT_RATE
    volume: float = DEFAULT_VOLUME
    pitch: int = DEFAULT_PITCH
    pause_ms: int = DEFAULT_PAUSE_MS
    emphasis: str = DEFAULT_EMPHASIS

    @staticmethod
    def defaults() -> VoiceTuning:
        return VoiceTuning()


def normalize_tuning(tuning: VoiceTuning) -> VoiceTuning:
    """Return a tuning with clamped numbers and a known emphasis level."""

    voice = tuning.voice.strip()
    if is_default_voice_query(voice):
        voice = ""
    rate = _as_int(tuning.rate, "speech.rate")
    if not RATE_MIN <= rate <= RATE_MAX:
        raise TuningError(
            f"speech.rate must be between {RATE_MIN} and {RATE_MAX} words per minute"
        )
    volume = _as_volume(tuning.volume)
    pitch = _as_int(tuning.pitch, "speech.pitch")
    if not PITCH_MIN <= pitch <= PITCH_MAX:
        raise TuningError(
            f"speech.pitch must be between {PITCH_MIN} and {PITCH_MAX}"
        )
    pause_ms = _as_int(tuning.pause_ms, "speech.pause_ms")
    if not PAUSE_MIN <= pause_ms <= PAUSE_MAX:
        raise TuningError(
            f"speech.pause_ms must be between {PAUSE_MIN} and {PAUSE_MAX}"
        )
    emphasis = str(tuning.emphasis or "").strip().lower()
    if emphasis not in EMPHASIS_LEVELS:
        raise TuningError("speech.emphasis must be none, mild, or strong")
    return VoiceTuning(
        voice=voice,
        rate=rate,
        volume=volume,
        pitch=pitch,
        pause_ms=pause_ms,
        emphasis=emphasis,
    )


def is_default_voice_query(query: str) -> bool:
    return query.strip().lower() in _DEFAULT_VOICE_QUERIES


def emphasis_label(value: str) -> str:
    return EMPHASIS_LABELS.get(value.strip().lower(), "None")


def emphasis_from_label(label: str) -> str:
    cleaned = label.strip().lower()
    for value, shown in EMPHASIS_LABELS.items():
        if cleaned == value or cleaned == shown.lower():
            return value
    raise TuningError("speech.emphasis must be none, mild, or strong")


def resolve_voice_name(query: str, available: list[str] | None = None) -> str:
    """Return the voice name to store. ``""`` means the engine default.

    When ``available`` is provided, a non-empty query must match one installed
    name. An exact match wins over a substring. ``available`` None means the
    voice list could not be read, so an allowed name is kept as written.
    """

    if is_default_voice_query(query):
        return ""
    cleaned = query.strip()
    if available is None:
        return cleaned
    names = _unique_names(available)
    exact = [name for name in names if name.lower() == cleaned.lower()]
    if exact:
        return exact[0]
    partial = [name for name in names if cleaned.lower() in name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise TuningError(
            f"Voice {query!r} matches more than one installed voice: "
            + ", ".join(partial)
            + ". Choose the full voice name."
        )
    known = ", ".join(names) or "(none)"
    raise TuningError(f"No installed voice matches {query!r}. Voices: {known}")


def voice_menu_labels(names: list[str], current: str) -> list[str]:
    """Picker labels. The engine default is first."""

    labels = [ENGINE_DEFAULT_VOICE]
    for name in _unique_names(names):
        if name not in labels:
            labels.append(name)
    if current and current not in labels:
        labels.append(current)
    return labels


def selected_voice_label(current: str, names: list[str]) -> str:
    if not current or is_default_voice_query(current):
        return ENGINE_DEFAULT_VOICE
    try:
        resolved = resolve_voice_name(current, names if names else None)
    except TuningError:
        return current
    return resolved or ENGINE_DEFAULT_VOICE


def prepare_utterance(text: str, tuning: VoiceTuning) -> tuple[str, bool]:
    """Return ``(spoken, uses_xml)`` for one line.

    ``uses_xml`` is true when SAPI must parse markup: a pitch offset, a pause,
    emphasis, or characters that would otherwise look like tags. Plain lines
    stay plain so the engine's normal speak path is unchanged.
    """

    tuning = normalize_tuning(tuning)
    raw = text.strip()
    if not raw:
        return "", False
    body = _xml_escape(raw)
    pitch = tuning.pitch
    if tuning.emphasis == "mild":
        body = f"<emph>{body}</emph>"
    elif tuning.emphasis == "strong":
        body = f"<emph>{body}</emph>"
        pitch = max(PITCH_MIN, min(PITCH_MAX, pitch + _STRONG_EMPHASIS_PITCH))
    if pitch != 0:
        body = f'<pitch absmiddle="{pitch}">{body}</pitch>'
    if tuning.pause_ms > 0:
        body = f'<silence msec="{int(tuning.pause_ms)}"/>{body}'
    return body, body != raw


def list_sapi_voice_names() -> list[str]:
    """Names of desktop SAPI voices. Empty when not on Windows or SAPI is down."""

    if sys.platform != "win32":
        return []
    try:
        import comtypes.client
    except ImportError:
        logger.warning("comtypes is not installed; speech voices cannot be listed.")
        return []
    try:
        category = comtypes.client.CreateObject("SAPI.SpObjectTokenCategory")
        category.SetId(SAPI_VOICES, False)
        tokens = category.EnumerateTokens()
    except Exception:
        logger.warning("Could not list SAPI voices", exc_info=True)
        return []
    names: list[str] = []
    for token in tokens:
        try:
            names.append(str(token.GetDescription()))
        except Exception:
            logger.debug("Skipping a SAPI voice with no description", exc_info=True)
    return _unique_names(names)


def _unique_names(names: list[str]) -> list[str]:
    chosen: list[str] = []
    for name in names:
        cleaned = name.strip()
        if cleaned and cleaned not in chosen:
            chosen.append(cleaned)
    return chosen


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TuningError(f"{label} must be an integer")
    return value


def _as_volume(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TuningError("speech.volume must be a number from 0.0 to 1.0")
    volume = round(float(value), 2)
    if not 0.0 <= volume <= 1.0:
        raise TuningError("speech.volume must be between 0.0 and 1.0")
    return volume
