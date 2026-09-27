"""Background speech queue with priority preemption.

Small lines wait their turn. A big moment (priority at or above the configured
floor, and higher than whatever is currently playing) interrupts it. Audio
never goes anywhere except the active backend.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from suit_o.config import ConfigError, is_disallowed_output_device
from suit_o.models import Utterance
from suit_o.preferences import clamp_volume
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.tuning import VoiceTuning, normalize_tuning

logger = logging.getLogger(__name__)

_MAX_PENDING = 8
_NO_DEVICE = object()
_NO_TUNING = object()
_NO_BACKEND = object()


@dataclass
class _Job:
    utterance: Utterance
    bypass_mute: bool = False
    tuning: VoiceTuning | None = None
    backend: SpeechBackend | None = None


class SpeechService:
    def __init__(self, backend: SpeechBackend, preempt_min_priority: int) -> None:
        self.backend = backend
        self.preempt_min_priority = preempt_min_priority
        self.history: list[Utterance] = []
        self._pending: list[_Job] = []
        self._current: Utterance | None = None
        self._current_bypass = False
        self._muted = False
        self._stop = False
        self._queued_volume: float | None = None
        self._queued_device: object = _NO_DEVICE
        self._queued_tuning: object = _NO_TUNING
        self._queued_backend: object = _NO_BACKEND
        self._current_speaker: SpeechBackend | None = None
        self._applying = False
        self._cv = threading.Condition()
        self._thread = threading.Thread(target=self._loop, name="suit-o-speech", daemon=True)
        self._started = False
        self.on_dropped: Callable[[Utterance], None] | None = None

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def submit(
        self,
        utterance: Utterance,
        *,
        bypass_mute: bool = False,
        tuning: VoiceTuning | None = None,
        backend: SpeechBackend | None = None,
    ) -> None:
        dropped: list[_Job] = []
        with self._cv:
            if self._stop or (self._muted and not bypass_mute):
                return
            override = None if tuning is None else normalize_tuning(tuning)
            self._pending.append(_Job(utterance, bypass_mute, override, backend))
            self._pending.sort(key=lambda item: -item.utterance.priority)
            if len(self._pending) > _MAX_PENDING:
                dropped = self._pending[_MAX_PENDING :]
                del self._pending[_MAX_PENDING :]
                logger.warning("Dropped %s queued line(s) above the speech cap", len(dropped))
            if (
                self._current is not None
                and not self._current_bypass
                and utterance.priority > self._current.priority
                and utterance.priority >= self.preempt_min_priority
            ):
                self.backend.stop()
            self._cv.notify()
        callback = self.on_dropped
        if callback is None:
            return
        for job in dropped:
            callback(job.utterance)

    def set_volume(self, volume: float) -> None:
        """Queue a volume change. It is applied on the speech thread."""

        volume_f = clamp_volume(volume)
        with self._cv:
            self._queued_volume = volume_f
            if self._queued_tuning is not _NO_TUNING:
                pending = self._queued_tuning
                self._queued_tuning = VoiceTuning(
                    voice=pending.voice,
                    rate=pending.rate,
                    volume=volume_f,
                    pitch=pending.pitch,
                    pause_ms=pending.pause_ms,
                    emphasis=pending.emphasis,
                )
            self._cv.notify()

    def set_output_device(self, name: str) -> None:
        """Queue a playback-device change. A microphone name is refused here."""

        cleaned = name.strip()
        if is_disallowed_output_device(cleaned):
            raise ConfigError(
                "speech.output_device looks like a microphone or a virtual cable "
                "into voice chat. Choose a playback device (headset or speakers), "
                "or leave it blank to use the Windows default playback device."
            )
        with self._cv:
            self._queued_device = cleaned
            self._cv.notify()

    def apply_tuning(self, tuning: VoiceTuning) -> None:
        """Queue voice, rate, pitch, pause, emphasis, and volume.

        Applied on the speech thread before the next line. Pitch and pause
        stay on the tuning object; each backend decides how to render them.
        """

        applied = normalize_tuning(tuning)
        with self._cv:
            self._queued_tuning = applied
            self._cv.notify()

    def preview(self, text: str, tuning: VoiceTuning | None = None) -> None:
        """Speak ``text`` now, even while muted, with an optional one-line tuning.

        The override is not stored. The next in-game line uses the last
        ``apply_tuning`` (or the backend's original settings).
        """

        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Preview needs a line to speak")
        self.submit(
            Utterance(event_type="preview", text=cleaned, priority=100),
            bypass_mute=True,
            tuning=tuning,
        )

    def preview_with(self, text: str, tuning: VoiceTuning | None, backend: SpeechBackend) -> None:
        """Speak one line through ``backend`` without making it the default.

        Used so a Voice-tab preview of an unsaved cloned voice does not switch
        in-game lines until the user saves.
        """

        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Preview needs a line to speak")
        self.submit(
            Utterance(event_type="preview", text=cleaned, priority=100),
            bypass_mute=True,
            tuning=tuning,
            backend=backend,
        )

    def set_backend(self, backend: SpeechBackend) -> None:
        """Swap the speech backend on the speech thread, between lines."""

        with self._cv:
            replaced = self._queued_backend
            self._queued_backend = backend
            self._cv.notify()
        if replaced is not _NO_BACKEND:
            try:
                replaced.close()  # type: ignore[attr-defined]
            except Exception:
                logger.exception("Could not close a replaced speech backend")

    def set_muted(self, muted: bool) -> None:
        with self._cv:
            self._muted = muted
            if muted:
                self._pending = [job for job in self._pending if job.bypass_mute]
                if self._current is not None and not self._current_bypass:
                    self.backend.stop()
            self._cv.notify_all()

    def wait_until(self, ready, timeout: float) -> bool:
        """Block until ``ready()`` is true and the queue is idle, or time out.

        Polls briefly so a caller can wait on work that happens outside this
        condition variable (the GSI worker's processed count, for example).
        """

        deadline = _now() + timeout
        while True:
            with self._cv:
                idle = (
                    not self._pending
                    and self._current is None
                    and not self._has_controls()
                    and not self._applying
                )
            if ready() and idle:
                return True
            remaining = deadline - _now()
            if remaining <= 0:
                return False
            with self._cv:
                self._cv.wait(min(remaining, 0.05))

    def interrupt(self) -> None:
        """Stop the line that is playing and drop anything still queued.

        The speech thread keeps running, so the next in-game line can still play.
        """

        with self._cv:
            self._pending.clear()
            speaker = self._current_speaker
            playing = self._current is not None
            self._cv.notify_all()
        if not playing:
            return
        self.backend.stop()
        if speaker is not None and speaker is not self.backend:
            try:
                speaker.stop()
            except Exception:
                logger.debug("Could not stop the active speech backend", exc_info=True)

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._pending.clear()
            queued = self._queued_backend
            self._queued_backend = _NO_BACKEND
            speaker = self._current_speaker
            self._cv.notify_all()
        if queued is not _NO_BACKEND:
            try:
                queued.close()  # type: ignore[attr-defined]
            except Exception:
                logger.exception("Could not close a queued speech backend")
        self.backend.stop()
        if speaker is not None and speaker is not self.backend:
            try:
                speaker.stop()
            except Exception:
                logger.exception("Could not stop the active speech backend")
        if self._started:
            self._thread.join(timeout=2)
        self.backend.close()

    def _has_controls(self) -> bool:
        return (
            self._queued_volume is not None
            or self._queued_device is not _NO_DEVICE
            or self._queued_tuning is not _NO_TUNING
            or self._queued_backend is not _NO_BACKEND
        )

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._pending and not self._stop and not self._has_controls():
                    self._cv.wait()
                if self._stop and not self._pending:
                    return
                volume = self._queued_volume
                device = self._queued_device
                tuning = self._queued_tuning
                backend = self._queued_backend
                self._queued_volume = None
                self._queued_device = _NO_DEVICE
                self._queued_tuning = _NO_TUNING
                self._queued_backend = _NO_BACKEND
                self._applying = (
                    volume is not None
                    or device is not _NO_DEVICE
                    or tuning is not _NO_TUNING
                    or backend is not _NO_BACKEND
                )
                job: _Job | None = None
                if self._pending:
                    job = self._pending.pop(0)
                    if self._muted and not job.bypass_mute:
                        job = None
                    else:
                        self._current = job.utterance
                        self._current_bypass = job.bypass_mute
            try:
                self._apply_controls(volume, device, tuning, backend)
            finally:
                with self._cv:
                    self._applying = False
                    self._cv.notify_all()
            if job is None:
                continue
            completed = False
            speaker = job.backend or self.backend
            with self._cv:
                self._current_speaker = speaker
            try:
                if job.tuning is None:
                    completed = bool(speaker.speak(job.utterance.text))
                else:
                    completed = bool(speaker.speak(job.utterance.text, tuning=job.tuning))
            except Exception:
                logger.exception("Speech backend failed")
            with self._cv:
                if completed and (not self._muted or job.bypass_mute):
                    self.history.append(job.utterance)
                self._current = None
                self._current_bypass = False
                self._current_speaker = None
                self._cv.notify_all()

    def _apply_controls(
        self,
        volume: float | None,
        device: object,
        tuning: object,
        backend: object,
    ) -> None:
        if backend is not _NO_BACKEND and backend is not self.backend:
            old = self.backend
            self.backend = backend  # type: ignore[assignment]
            try:
                old.close()
            except Exception:
                logger.exception("Could not close the previous speech backend")
        if device is not _NO_DEVICE:
            try:
                self.backend.set_output_device(str(device))
            except Exception:
                logger.exception("Could not apply the speech output device")
        if tuning is not _NO_TUNING:
            try:
                self.backend.apply_tuning(tuning)
            except Exception:
                logger.exception("Could not apply voice tuning")
        if volume is not None:
            try:
                self.backend.set_volume(volume)
            except Exception:
                logger.exception("Could not apply speech volume")


def _now() -> float:
    import time

    return time.monotonic()
