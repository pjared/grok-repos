"""Cloned-voice backend. Matches play pre-rendered WAV files only.

Stock lines are written under the profile's ``cache/`` folder when the voice
is built, when those lines change, and when this voice's tuning changes.
``speak`` never calls the model. A missing file is spoken with the Windows
SAPI voice instead. Live synthesis is reserved for preview.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import wave
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
        fallback: SpeechBackend | None = None,
    ) -> None:
        self._settings = settings
        self._synthesizer = synthesizer or _default_synthesize
        self._player = player or _default_player
        self._fallback = fallback
        self._cancel = threading.Event()
        self._urgent = threading.Event()
        self._round_live = threading.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._live = False
        self._warmer: threading.Thread | None = None
        self._warming = False
        self._pending_lines: list[str] | None = None
        self._writing: set[Path] = set()
        self.synthesized: list[str] = []
        self.fallback_spoken: list[str] = []

    def set_round_live(self, live: bool) -> None:
        """Pause pre-rendering while a round's phase is live."""

        if live:
            self._round_live.set()
        else:
            self._round_live.clear()

    def allow_live_synthesis(self) -> None:
        """Let this instance synthesize. Used only for Voice-tab preview."""

        self._live = True

    def speak(self, text: str, tuning: VoiceTuning | None = None) -> bool:
        self._urgent.set()
        previous = None
        if tuning is not None:
            previous = self._snapshot()
            self.apply_tuning(tuning)
        try:
            if self._live:
                return self._speak_preview(text)
            return self._speak_cached(text)
        finally:
            self._urgent.clear()
            if previous is not None:
                self.apply_tuning(previous)

    def prerender(self, lines: list[str], *, wait: bool = False) -> None:
        """Write a WAV for every stock line. Skips files that already match.

        Runs off the speech thread. Pauses while a match line is playing and
        drops the model so that playback does not keep the GPU. Calling this
        again after a tuning or script change fills whatever is missing.
        A render that is already running keeps that work; a second thread is
        not started.
        """

        pending = []
        seen: set[str] = set()
        for line in lines:
            cleaned = line.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                pending.append(cleaned)

        with self._lock:
            self._pending_lines = pending
            warmer = self._warmer
            if not self._warming:
                self._warming = True
                warmer = threading.Thread(target=self._warm, name="suit-o-voice-cache", daemon=True)
                self._warmer = warmer
                warmer.start()
        if wait and warmer is not None:
            warmer.join()

    def _warm(self) -> None:
        """Render queued lines on the one cache thread. A newer list replaces the queue."""

        while not self._closed:
            with self._lock:
                batch = self._pending_lines
                self._pending_lines = None
                if not batch:
                    self._warming = False
                    return
            for line in batch:
                if self._closed:
                    break
                while (self._urgent.is_set() or self._round_live.is_set()) and not self._closed:
                    _release_model()
                    time.sleep(0.05)
                if self._closed:
                    break
                try:
                    self._write_cache(line, self._snapshot())
                except Exception:
                    logger.exception("Could not pre-render a stock line")
            else:
                _release_model()
                continue
            break
        _release_model()
        with self._lock:
            self._warming = False

    def wait_prerender(self, timeout: float) -> bool:
        warmer = self._warmer
        if warmer is None:
            return True
        warmer.join(timeout)
        return not warmer.is_alive()

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
        fallback = self._fallback
        if fallback is not None:
            try:
                fallback.stop()
            except Exception:
                logger.debug("SAPI fallback stop failed", exc_info=True)

    def close(self) -> None:
        self._closed = True
        self.stop()
        warmer = self._warmer
        if warmer is not None and warmer is not threading.current_thread():
            warmer.join(timeout=1)
        fallback = self._fallback
        if fallback is not None:
            try:
                fallback.close()
            except Exception:
                logger.debug("SAPI fallback close failed", exc_info=True)
        _release_model()

    def _speak_cached(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            self._cancel.clear()
            return True
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        self._refuse_output_device()
        try:
            path = self._cache_path(cleaned, self._snapshot())
        except RuntimeError:
            path = None
        if path is not None and path.is_file():
            loaded = self._read_cached(path)
            if loaded is not None:
                return self._play(loaded[0], loaded[1])
            logger.info("Pre-rendered clone for %r could not be read; using the Windows voice", cleaned)
            return self._speak_fallback(cleaned)
        logger.info("No pre-rendered clone for %r; using the Windows voice", cleaned)
        return self._speak_fallback(cleaned)

    def _speak_preview(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            self._cancel.clear()
            return True
        if self._cancel.is_set():
            self._cancel.clear()
            return False
        self._refuse_output_device()
        tuning = self._snapshot()
        path = self._cache_path(cleaned, tuning)
        try:
            if path.is_file():
                samples, rate = read_wav(path)
            else:
                samples, rate = self._synthesize(cleaned, tuning)
            return self._play(samples, rate)
        finally:
            _release_model()

    def _speak_fallback(self, text: str) -> bool:
        self.fallback_spoken.append(text)
        fallback = self._fallback_backend()
        tuning = self._snapshot()
        sapi = VoiceTuning(
            voice="",
            rate=tuning.rate,
            volume=tuning.volume,
            pitch=tuning.pitch,
            pause_ms=tuning.pause_ms,
            emphasis=tuning.emphasis,
        )
        try:
            fallback.set_output_device(self._settings.output_device)
        except Exception:
            logger.debug("Could not aim the Windows voice at the output device", exc_info=True)
        try:
            return bool(fallback.speak(text, tuning=sapi))
        except TypeError:
            return bool(fallback.speak(text))

    def _fallback_backend(self) -> SpeechBackend:
        if self._fallback is not None:
            return self._fallback
        from suit_o.speech.pyttsx3_backend import Pyttsx3Backend

        tuning = self._snapshot()
        self._fallback = Pyttsx3Backend(
            SpeechConfig(
                backend="pyttsx3",
                voice="",
                rate=tuning.rate,
                volume=tuning.volume,
                output_device=self._settings.output_device,
                pitch=tuning.pitch,
                pause_ms=tuning.pause_ms,
                emphasis=tuning.emphasis,
            )
        )
        return self._fallback

    def _write_cache(self, text: str, tuning: VoiceTuning) -> None:
        path = self._cache_path(text, tuning)
        with self._lock:
            if path.is_file() or path in self._writing:
                return
            self._writing.add(path)
        try:
            samples, rate = self._synthesize(text, tuning)
            shaped = shape_waveform(samples, rate, tuning)
            temporary = path.with_name(path.name + ".partial")
            with self._lock:
                if self._closed or path.is_file():
                    return
                write_wav(temporary, shaped, rate)
                os.replace(temporary, path)
        finally:
            temporary = path.with_name(path.name + ".partial")
            if temporary.exists() and not path.is_file():
                try:
                    temporary.unlink()
                except OSError:
                    pass
            with self._lock:
                self._writing.discard(path)

    def _read_cached(self, path: Path) -> tuple[list[float], int] | None:
        try:
            samples, rate = read_wav(path)
        except (OSError, ValueError, EOFError, wave.Error):
            return None
        if rate < 1 or not samples:
            return None
        return samples, rate

    def _synthesize(self, text: str, tuning: VoiceTuning) -> tuple[list[float], int]:
        profile = self._profile()
        samples, rate = self._synthesizer(text, profile.prompt_wav, tuning.emphasis)
        self.synthesized.append(text)
        if self._live:
            return shape_waveform(samples, rate, tuning), rate
        return samples, rate

    def _play(self, samples: list[float], rate: int) -> bool:
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

    def _cache_path(self, text: str, tuning: VoiceTuning) -> Path:
        profile = self._profile()
        folder = profile.directory / "cache"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{cache_key(text, tuning)}.wav"

    def _refuse_output_device(self) -> None:
        if is_disallowed_output_device(self._settings.output_device):
            raise RuntimeError(
                f"Refusing playback device {self._settings.output_device!r}. "
                "It looks like a microphone or a virtual cable into voice chat."
            )

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


def _release_model() -> None:
    try:
        from suit_o.voice.engine import release_model
    except ImportError:
        return
    release_model()
