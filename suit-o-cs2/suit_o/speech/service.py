"""Background speech queue with priority preemption.

Small lines wait their turn. A big moment (priority at or above the configured
floor, and higher than whatever is currently playing) interrupts it. Audio
never goes anywhere except the active backend.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from suit_o.config import ConfigError, is_disallowed_output_device
from suit_o.models import Utterance
from suit_o.preferences import clamp_volume
from suit_o.speech.backend import SpeechBackend

logger = logging.getLogger(__name__)

_MAX_PENDING = 8
_NO_DEVICE = object()


@dataclass
class _Job:
    utterance: Utterance
    bypass_mute: bool = False


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
        self._applying = False
        self._cv = threading.Condition()
        self._thread = threading.Thread(target=self._loop, name="suit-o-speech", daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def submit(self, utterance: Utterance, *, bypass_mute: bool = False) -> None:
        with self._cv:
            if self._stop or (self._muted and not bypass_mute):
                return
            self._pending.append(_Job(utterance, bypass_mute))
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

    def set_volume(self, volume: float) -> None:
        """Queue a volume change. It is applied on the speech thread."""

        volume_f = clamp_volume(volume)
        with self._cv:
            self._queued_volume = volume_f
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

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._pending.clear()
            self._cv.notify_all()
        self.backend.stop()
        if self._started:
            self._thread.join(timeout=2)
        self.backend.close()

    def _has_controls(self) -> bool:
        return self._queued_volume is not None or self._queued_device is not _NO_DEVICE

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._pending and not self._stop and not self._has_controls():
                    self._cv.wait()
                if self._stop and not self._pending:
                    return
                volume = self._queued_volume
                device = self._queued_device
                self._queued_volume = None
                self._queued_device = _NO_DEVICE
                self._applying = volume is not None or device is not _NO_DEVICE
                job: _Job | None = None
                if self._pending:
                    job = self._pending.pop(0)
                    if self._muted and not job.bypass_mute:
                        job = None
                    else:
                        self._current = job.utterance
                        self._current_bypass = job.bypass_mute
            try:
                self._apply_controls(volume, device)
            finally:
                with self._cv:
                    self._applying = False
                    self._cv.notify_all()
            if job is None:
                continue
            completed = False
            try:
                completed = bool(self.backend.speak(job.utterance.text))
            except Exception:
                logger.exception("Speech backend failed")
            with self._cv:
                if completed and (not self._muted or job.bypass_mute):
                    self.history.append(job.utterance)
                self._current = None
                self._current_bypass = False
                self._cv.notify_all()

    def _apply_controls(self, volume: float | None, device: object) -> None:
        if volume is not None:
            try:
                self.backend.set_volume(volume)
            except Exception:
                logger.exception("Could not apply speech volume")
        if device is not _NO_DEVICE:
            try:
                self.backend.set_output_device(str(device))
            except Exception:
                logger.exception("Could not apply the speech output device")


def _now() -> float:
    import time

    return time.monotonic()
