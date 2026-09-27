"""Cloned-voice backend. Chatterbox is loaded only when a line is synthesized.

Stock lines are cached as WAV files under the profile's ``cache/`` folder so
a match can play them without waiting on the model again. Synthesis runs on
the speech thread, never on the GUI thread. A background warm-up can fill
the cache ahead of time and gets out of the way when a live line arrives.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from suit_o.config import PROJECT_ROOT, SpeechConfig, is_disallowed_output_device
from suit_o.preferences import clamp_volume
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.tuning import VoiceTuning, normalize_tuning
from suit_o.voice.profile import ProfileError, find_profile
from suit_o.voice.runtime import INSTALL_HINT, MODEL_ID
from suit_o.voice.wav import read_wav, shape_waveform, write_wav

logger = logging.getLogger(__name__)

Synthesizer = Callable[[str, Path, str], tuple[list[float], int]]
Player = Callable[[list[float], int, str, float, threading.Event], bool]


class CloneSpeechBackend(SpeechBackend):
    def __init__(
        self,
        settings: SpeechConfig,
        *,
        synthesizer: Synthesizer | None = None,
        player: Player | None = None,
    ) -> None:
        self._settings = settings
        self._synthesizer = synthesizer or _default_synthesize
        self._player = player or _default_player
        self._cancel = threading.Event()
        self._urgent = threading.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._warmer: threading.Thread | None = None
        self.synthesized: list[str] = []

    def speak(self, text: str, tuning: VoiceTuning | None = None) -> bool:
        self._urgent.set()
        previous = None
        if tuning is not None:
            previous = self._snapshot()
            self.apply_tuning(tuning)
        try:
            return self._speak_current(text)
        finally:
            self._urgent.clear()
            if previous is not None:
                self.apply_tuning(previous)

    def warm_stock_lines(self, lines: list[str], *, wait: bool = False) -> None:
        """Fill the cache off to the side. Live speech sets ``_urgent`` and cuts in."""

        pending = [line.strip() for line in lines if line and line.strip()]

        def run() -> None:
            for line in pending:
                if self._closed:
                    return
                while self._urgent.is_set() and not self._closed:
                    time.sleep(0.05)
                if self._closed:
                    return
                try:
                    with self._lock:
                        if self._closed or self._urgent.is_set():
                            continue
                        self._cached_samples(line, self._snapshot())
                except Exception:
                    logger.exception("Could not cache a stock line")

        self._warmer = threading.Thread(target=run, name="suit-o-voice-cache", daemon=True)
        self._warmer.start()
        if wait:
            self._warmer.join()

    def apply_tuning(self, tuning: object) -> None:
        applied = normalize_tuning(tuning)  # type: ignore[arg-type]
        self._settings.voice = applied.voice
        self._settings.rate = applied.rate
        self._settings.volume = applied.volume
        self._settings.pitch = applied.pitch
        self._settings.pause_ms = applied.pause_ms
        self._settings.emphasis = applied.emphasis

    def set_volume(self, volume: float) -> None:
        self._settings.volume = clamp_volume(volume)

    def set_output_device(self, name: str) -> None:
        cleaned = name.strip()
        if is_disallowed_output_device(cleaned):
            raise RuntimeError(
                f"Refusing playback device {cleaned!r}. It looks like a microphone "
                "or a virtual cable into voice chat."
            )
        self._settings.output_device = cleaned

    def stop(self) -> None:
        self._cancel.set()
        self._urgent.set()

    def close(self) -> None:
        self._closed = True
        self.stop()
        warmer = self._warmer
        if warmer is not None and warmer is not threading.current_thread():
            warmer.join(timeout=1)

    def _speak_current(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            self._cancel.clear()
            return True
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        if is_disallowed_output_device(self._settings.output_device):
            raise RuntimeError(
                f"Refusing playback device {self._settings.output_device!r}. "
                "It looks like a microphone or a virtual cable into voice chat."
            )
        with self._lock:
            samples, rate = self._cached_samples(cleaned, self._snapshot())
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        finished = self._player(
            samples,
            rate,
            self._settings.output_device,
            float(self._settings.volume),
            self._cancel,
        )
        cancelled = self._cancel.is_set()
        self._cancel.clear()
        return bool(finished) and not cancelled

    def _cached_samples(self, text: str, tuning: VoiceTuning) -> tuple[list[float], int]:
        profile = self._profile()
        path = profile.directory / "cache" / f"{cache_key(text, tuning)}.wav"
        if path.is_file():
            return read_wav(path)
        samples, rate = self._synthesizer(text, profile.prompt_wav, tuning.emphasis)
        self.synthesized.append(text)
        shaped = shape_waveform(samples, rate, tuning)
        write_wav(path, shaped, rate)
        return shaped, rate

    def _profile(self):
        root = Path(self._settings.voices_dir) if self._settings.voices_dir else PROJECT_ROOT / "voices"
        try:
            return find_profile(root, self._settings.voice)
        except ProfileError as exc:
            raise RuntimeError(str(exc)) from exc

    def _snapshot(self) -> VoiceTuning:
        return VoiceTuning(
            voice=self._settings.voice,
            rate=self._settings.rate,
            volume=float(self._settings.volume),
            pitch=self._settings.pitch,
            pause_ms=self._settings.pause_ms,
            emphasis=self._settings.emphasis,
        )


def cache_key(text: str, tuning: VoiceTuning) -> str:
    """Identity of a rendered line. Volume is left out so the slider stays live."""

    payload = "\n".join(
        [
            MODEL_ID,
            str(tuning.rate),
            str(tuning.pitch),
            str(tuning.pause_ms),
            tuning.emphasis,
            text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _default_synthesize(text: str, prompt_wav: Path, emphasis: str) -> tuple[list[float], int]:
    try:
        from suit_o.voice.engine import synthesize
    except ImportError as exc:
        raise RuntimeError(INSTALL_HINT) from exc
    return synthesize(text, prompt_wav, emphasis)


def _default_player(
    samples: list[float],
    sample_rate: int,
    output_device: str,
    volume: float,
    cancel: threading.Event,
) -> bool:
    from suit_o.voice.capture import play_samples

    return play_samples(samples, sample_rate, output_device, volume=volume, cancel=cancel)
