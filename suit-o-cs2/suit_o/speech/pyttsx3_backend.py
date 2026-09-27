"""Offline speech via pyttsx3 (SAPI on Windows).

The engine is created on the speech thread. Audio goes to a playback device:
the Windows default endpoint, or a configured SAPI AudioOutput match. This
backend never selects a capture device and never writes microphone audio.
"""

from __future__ import annotations

import logging
import sys
import threading

from suit_o.config import SpeechConfig, is_disallowed_output_device
from suit_o.preferences import clamp_volume
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.devices import (
    DeviceSelectionError,
    enumerate_sapi_playback_devices,
    match_voice,
    matching_playback_devices,
)

logger = logging.getLogger(__name__)


class Pyttsx3Backend(SpeechBackend):
    def __init__(self, settings: SpeechConfig) -> None:
        self._settings = settings
        self._engine = None
        self._cancel = threading.Event()
        self._ready = False
        self._device_applied = False

    def speak(self, text: str) -> bool:
        self._ensure_engine()
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        assert self._engine is not None
        self._engine.say(text)
        self._engine.runAndWait()
        cancelled = self._cancel.is_set()
        self._cancel.clear()
        return not cancelled

    def stop(self) -> None:
        self._cancel.set()
        engine = self._engine
        if engine is None:
            return
        try:
            engine.stop()
        except Exception:
            logger.debug("pyttsx3 stop failed", exc_info=True)

    def close(self) -> None:
        self.stop()
        self._discard_engine()

    def set_volume(self, volume: float) -> None:
        """Store the volume and apply it if the engine already exists.

        The speech thread calls this between lines. The next ``say`` uses the
        new level, including the first line if the engine has not started yet.
        """

        self._settings.volume = clamp_volume(volume)
        engine = self._engine
        if engine is None:
            return
        engine.setProperty("volume", self._settings.volume)  # type: ignore[attr-defined]

    def set_output_device(self, name: str) -> None:
        """Switch playback endpoints. An empty name returns to the Windows default.

        SAPI reads the endpoint when the engine is created, so an engine that
        is already open is discarded and built again on the next line. A
        microphone or virtual-cable name is refused and the previous choice
        stays in place.
        """

        cleaned = name.strip()
        if is_disallowed_output_device(cleaned):
            raise RuntimeError(
                f"Refusing playback device {cleaned!r}. It looks like a microphone "
                "or a virtual cable into voice chat. Leave speech.output_device blank "
                "or choose a headset/speaker playback name."
            )
        unchanged = cleaned == self._settings.output_device
        if unchanged and (self._engine is None or self._device_applied):
            self._settings.output_device = cleaned
            return
        self._settings.output_device = cleaned
        self._device_applied = False
        if self._engine is not None:
            self._discard_engine()

    def _ensure_engine(self) -> None:
        if self._ready:
            return
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError(
                "pyttsx3 is not installed. From the suit-o-cs2 folder run: "
                "pip install -r requirements.txt"
            ) from exc
        try:
            engine = pyttsx3.init()
        except Exception as exc:
            raise RuntimeError(
                "Could not start the speech engine. On Windows, install a "
                "desktop speech voice under Settings > Time & language > Speech, "
                "then start Suit-O again."
            ) from exc
        engine.setProperty("rate", self._settings.rate)
        engine.setProperty("volume", self._settings.volume)
        try:
            self._apply_voice(engine)
            self._apply_output_device(engine)
        except Exception:
            try:
                engine.stop()
            except Exception:
                logger.debug("pyttsx3 cleanup after setup failure", exc_info=True)
            raise
        self._engine = engine
        self._ready = True
        self._device_applied = True

    def _apply_voice(self, engine: object) -> None:
        query = self._settings.voice
        if not query:
            logger.info("Speech voice: engine default")
            return
        voices = engine.getProperty("voices") or []  # type: ignore[attr-defined]
        pairs = [(getattr(voice, "name", "") or "", getattr(voice, "id", "") or "") for voice in voices]
        try:
            voice_id = match_voice(pairs, query)
        except DeviceSelectionError as exc:
            logger.warning("%s Using the default voice.", exc)
            return
        if voice_id:
            engine.setProperty("voice", voice_id)  # type: ignore[attr-defined]
            logger.info("Speech voice set to match %r", query)

    def _discard_engine(self) -> None:
        engine = self._engine
        self._engine = None
        self._ready = False
        self._device_applied = False
        if engine is None:
            return
        try:
            engine.stop()
        except Exception:
            logger.debug("pyttsx3 discard failed", exc_info=True)

    def _apply_output_device(
        self,
        engine: object,
        devices: list[tuple[str, object]] | None = None,
    ) -> None:
        query = self._settings.output_device
        if not query:
            logger.info("Speech output: Windows default playback device")
            return
        if devices is None:
            if sys.platform != "win32":
                logger.warning(
                    "speech.output_device is applied through Windows SAPI only. "
                    "Using the default playback device on this platform."
                )
                return
            try:
                devices = enumerate_sapi_playback_devices()
            except Exception as exc:
                logger.warning(
                    "Could not list playback devices (%s). Using the Windows default.",
                    exc,
                )
                return
        tts = _sapi_voice(engine)
        if tts is None:
            logger.warning("SAPI handle unavailable; using the default playback device.")
            return
        try:
            matches = matching_playback_devices(devices, query)
        except DeviceSelectionError as exc:
            logger.warning("%s Using the Windows default playback device.", exc)
            return
        if not matches:
            known = ", ".join(name for name, _token in devices) or "(none)"
            logger.warning(
                "No playback device matches %r. Playback devices: %s. "
                "Using the Windows default playback device.",
                query,
                known,
            )
            return
        if len(matches) > 1:
            logger.warning(
                "speech.output_device %r matches %s playback devices (%s). Using %r.",
                query,
                len(matches),
                ", ".join(name for name, _token in matches),
                matches[0][0],
            )
        token = matches[0][1]
        description = ""
        get_description = getattr(token, "GetDescription", None)
        if callable(get_description):
            description = str(get_description())
        if is_disallowed_output_device(description):
            raise RuntimeError(
                f"Refusing playback device {description!r}. It looks like a microphone "
                "or a virtual cable into voice chat. Leave speech.output_device blank "
                "or choose a headset/speaker playback name."
            )
        tts.AudioOutput = token
        logger.info("Speech output device: %s", description or query)


def _sapi_voice(engine: object):
    proxy = getattr(engine, "proxy", None)
    driver = getattr(proxy, "_driver", None)
    return getattr(driver, "_tts", None)
