"""Wire the GSI server, event detector, line provider, and speech queue."""

from __future__ import annotations

import hashlib
import logging
import sys
import threading
import time

import yaml
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue

from suit_o.config import PROJECT_ROOT, Config, ConfigError, SpeechConfig
from suit_o.events.detector import EventDetector
from suit_o.gsi.parse import parse_payload
from suit_o.gsi.server import GsiServer
from suit_o.lines.provider import LineProvider, YamlLineProvider
from suit_o.local_config import store_personal_settings
from suit_o.reload import restart_is_blocked
from suit_o.models import EventType, GameEvent, Utterance
from suit_o.lineups.deck import DeckView, LineupDeck
from suit_o.preferences import clamp_volume
from suit_o.speech.backend import SpeechBackend
from suit_o.speech.chat_render import ChatRenderer
from suit_o.speech.devices import (
    list_output_device_names,
    resolve_output_device,
    selectable_playback_names,
)
from suit_o.lines.provider import stock_line_texts
from suit_o.speech.clone_backend import CloneSpeechBackend
from suit_o.speech.factory import create_backend
from suit_o.speech.pyttsx3_backend import Pyttsx3Backend
from suit_o.speech.service import SpeechService
from suit_o.speech.tuning import (
    VoiceTuning,
    list_sapi_voice_names,
    normalize_tuning,
    resolve_voice_name,
)
from suit_o.voice.profile import (
    clone_label,
    is_clone_label,
    list_profiles,
    profile_name_from_label,
)
from suit_o.voice.runtime import INSTALL_HINT, runtime_status

logger = logging.getLogger(__name__)

# Spoken by the desktop window's Test voice button. It is not a game event.
TEST_VOICE_LINE = (
    "Helpful tip: if you can hear this, that output device is the one. "
    "I will just stand in the headset."
)

_LOG_LIMIT = 200
# A game line still waiting this many seconds is dropped, not spoken late.
GAME_LINE_MAX_AGE = 6.0


@dataclass(frozen=True)
class Activity:
    """One line for the desktop window's scrolling log."""

    seq: int
    at: float
    message: str


@dataclass(frozen=True)
class ListenerSnapshot:
    """Point-in-time state the desktop window paints. No tkinter types."""

    listening: bool
    host: str
    port: int
    muted: bool
    volume: float
    output_device: str
    received: int
    spoken: int
    seconds_since_payload: float | None
    activity: tuple[Activity, ...]


@dataclass(frozen=True)
class ReloadResult:
    """Outcome of applying config and content without restarting the process."""

    ok: bool
    message: str
    restart: bool = False
    applied: bool = False


class SuitOApp:
    def __init__(
        self,
        config: Config,
        *,
        backend: SpeechBackend | None = None,
        line_provider: LineProvider | None = None,
        clock=None,
        config_path: Path | None = None,
        output_devices: Callable[[], list[str]] | None = None,
        voices: Callable[[], list[str]] | None = None,
        voices_dir: Path | None = None,
        lineups_dir: Path | None = None,
        pack_dir: Path | None = None,
        backend_factory: Callable[[SpeechConfig], SpeechBackend] | None = None,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self._output_devices = output_devices
        self._voices = voices
        self.voices_dir = voices_dir or (PROJECT_ROOT / "voices")
        self.lineups_dir = lineups_dir or (PROJECT_ROOT / "lineups")
        self.pack_dir = pack_dir or (PROJECT_ROOT / "lineup-data")
        self.lineups = LineupDeck(self.lineups_dir, pack_dir=self.pack_dir)
        self.lineups.set_enabled(config.lineups.enabled)
        self.lineups.set_smokes_only(config.lineups.smokes_only)
        self._match_activity: str | None = None
        self._match_round: str | None = None
        self._match_map_phase: str | None = None
        self._backend_factory = backend_factory or create_backend
        if not config.speech.voices_dir:
            config.speech.voices_dir = str(self.voices_dir)
        self._clock = clock or time.monotonic
        self.backend = backend if backend is not None else self._backend_factory(config.speech)
        self.speech = SpeechService(self.backend, config.preempt_min_priority)
        self.speech.on_dropped = self._on_speech_dropped
        self.speech.on_stale = self._on_speech_stale
        self.lines = line_provider or YamlLineProvider.from_file(
            config.lines_path,
            cooldowns=config.cooldowns,
            default_cooldown=config.default_cooldown,
            min_interval=config.min_interval,
            preempt_min_priority=config.preempt_min_priority,
            muted=config.mute,
        )
        if hasattr(self.lines, "set_muted"):
            self.lines.set_muted(config.mute)
        if hasattr(self.lines, "set_chattiness"):
            self.lines.set_chattiness(config.chattiness)
        self.detector = EventDetector(config.thresholds)
        self._queue: Queue = Queue(maxsize=128)
        self.processed = 0
        self._httpd: GsiServer | None = None
        self._http_thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._did_stop = False
        self._started = False
        self.last_payload_at: float | None = None
        self._activity: deque[Activity] = deque(maxlen=_LOG_LIMIT)
        self._activity_seq = 0
        self._activity_lock = threading.Lock()
        self._lines_stamp: str | None = None
        self._lines_checked = 0.0
        self._renderers: list[CloneSpeechBackend] = []
        self._chat_renderer = ChatRenderer()
        self._on_settings_saved: Callable[[], None] | None = None

    def start(self, *, console: bool = False) -> None:
        if self._started:
            return
        self._started = True
        self._note_optional_installs()
        self.speech.start()
        self.speech.apply_tuning(self.current_tuning())
        self.speech.set_muted(bool(getattr(self.lines, "muted", self.config.mute)))
        self._lines_stamp = self._stock_lines_stamp()
        if isinstance(self.backend, CloneSpeechBackend):
            self.backend.apply_tuning(self.current_tuning())
            self._prerender_clone(self.backend)
        self._worker = threading.Thread(target=self._worker_loop, name="suit-o-gsi", daemon=True)
        self._worker.start()
        self._httpd = GsiServer(
            self.config.server.host,
            self.config.server.port,
            self.config.server.token,
            self._queue,
            self.toggle_mute,
            self.status,
            on_rejected=self._on_gsi_rejected,
        )
        self._http_thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="suit-o-http",
            daemon=True,
        )
        self._http_thread.start()
        host, port = self.server_address
        self._record(f"Listener up at http://{host}:{port}")
        if console and sys.stdin is not None and sys.stdin.isatty():
            threading.Thread(target=self._stdin_loop, name="suit-o-console", daemon=True).start()

    @property
    def server_address(self) -> tuple[str, int]:
        if self._httpd is None:
            raise RuntimeError("Suit-O is not listening yet")
        host, port = self._httpd.server_address[:2]
        return str(host), int(port)

    def wait_for_payloads(self, count: int, timeout: float = 5.0) -> bool:
        return self.speech.wait_until(lambda: self.processed >= count, timeout)

    def wait_forever(self) -> None:
        while not self._did_stop:
            time.sleep(0.2)

    def toggle_mute(self) -> bool:
        return self.set_muted(not self.muted)

    @property
    def muted(self) -> bool:
        return bool(getattr(self.lines, "muted", False))

    def set_muted(self, muted: bool) -> bool:
        muted = bool(muted)
        if muted == self.muted:
            return muted
        if hasattr(self.lines, "set_muted"):
            self.lines.set_muted(muted)
        else:
            self.lines.muted = muted
        self.speech.set_muted(muted)
        self.config.mute = muted
        self._record("Suit-O is muted" if muted else "Suit-O is listening")
        return muted

    def set_volume(self, volume: float) -> float:
        """Apply Suit-O's own volume, from 0.0 to 1.0. Does not touch the game."""

        applied = clamp_volume(volume)
        self.config.speech.volume = applied
        self.speech.set_volume(applied)
        return applied

    def output_device_names(self) -> list[str]:
        """SAPI playback names, or the injected list used by tests.

        Microphones and virtual cables are removed.
        """

        if self._output_devices is not None:
            listed = list(self._output_devices())
        else:
            listed = list_output_device_names()
        return selectable_playback_names(listed)

    def set_output_device(self, query: str) -> str:
        """Select a playback device and apply it to the next spoken line.

        ``""`` or "Windows default" uses the Windows default endpoint. The
        stored value is the device's full name when the current device list
        contains a match. A microphone name is refused and nothing changes.
        """

        names = self.output_device_names()
        resolved = resolve_output_device(query, names if names else None)
        changed = resolved != self.config.speech.output_device
        self.speech.set_output_device(resolved)
        self.config.speech.output_device = resolved
        if changed:
            if resolved:
                self._record(f"Output device: {resolved}")
            else:
                self._record("Output device: Windows default playback device")
        return resolved

    def voice_profiles(self):
        return list_profiles(self.voices_dir)

    def current_voice_label(self) -> str:
        if self.config.speech.backend == "clone" and self.config.speech.voice:
            return clone_label(self.config.speech.voice)
        from suit_o.speech.tuning import selected_voice_label

        return selected_voice_label(self.config.speech.voice, self.voice_names())

    def voice_picker_labels(self) -> list[str]:
        from suit_o.speech.tuning import voice_menu_labels

        saved = "" if self.config.speech.backend == "clone" else self.config.speech.voice
        labels = voice_menu_labels(self.voice_names(), saved)
        for profile in self.voice_profiles():
            if profile.label not in labels:
                labels.append(profile.label)
        current = self.current_voice_label()
        if current and current not in labels:
            labels.append(current)
        return labels

    def voice_names(self) -> list[str]:
        """Installed SAPI voice names, or the injected list used by tests."""

        if self._voices is not None:
            listed = self._voices()
        else:
            listed = list_sapi_voice_names()
        names: list[str] = []
        for name in listed:
            cleaned = str(name).strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)
        return names

    def current_tuning(self) -> VoiceTuning:
        speech = self.config.speech
        return VoiceTuning(
            voice=speech.voice,
            rate=speech.rate,
            volume=float(speech.volume),
            pitch=speech.pitch,
            pause_ms=speech.pause_ms,
            emphasis=speech.emphasis,
        )

    def apply_tuning(self, tuning: VoiceTuning) -> VoiceTuning:
        """Validate a voice panel snapshot and use it for later in-game lines.

        Does not write ``config.yaml``. Call :meth:`save_preferences` for that.
        """

        applied = self._resolve_tuning(tuning)
        self._store_tuning(applied)
        self.speech.apply_tuning(applied)
        return applied

    def apply_saved_voice(self, tuning: VoiceTuning, label: str) -> VoiceTuning:
        """Save a Voice-tab choice, including a cloned profile.

        A cloned label switches ``speech.backend`` to ``clone`` unless this
        process is the in-memory stub used by tests and the simulator. Picking
        a SAPI voice again leaves a previous clone and returns to pyttsx3.
        """

        if is_clone_label(label):
            name = profile_name_from_label(label)
            names = [profile.name for profile in self.voice_profiles()]
            if not names:
                raise ConfigError("No cloned voice has been built yet")
            applied = self._resolve_tuning(
                VoiceTuning(
                    voice=name,
                    rate=tuning.rate,
                    volume=tuning.volume,
                    pitch=tuning.pitch,
                    pause_ms=tuning.pause_ms,
                    emphasis=tuning.emphasis,
                ),
                names=names,
            )
            if self.config.speech.backend != "stub":
                self.config.speech.backend = "clone"
        else:
            applied = self._resolve_tuning(tuning)
            if self.config.speech.backend == "clone":
                self.config.speech.backend = "pyttsx3"
        self._store_tuning(applied)
        self._install_backend()
        return applied

    def reset_tuning(self) -> VoiceTuning:
        """Restore the stock voice knobs. A cloned backend returns to SAPI."""

        applied = self.apply_tuning(VoiceTuning.defaults())
        if self.config.speech.backend == "clone":
            self.config.speech.backend = "pyttsx3"
            self.config.speech.voice = ""
            self._install_backend()
        return applied

    def preview_voice(self, text: str, tuning: VoiceTuning | None = None, *, label: str | None = None) -> str:
        """Speak ``text`` on the current output device, even when muted.

        ``tuning`` is used for this line only. Saved settings stay as they are
        until :meth:`apply_tuning`.
        """

        line = (text or "").strip()
        if not line:
            raise ValueError("Preview needs a line to speak")
        if len(line) > 500:
            line = line[:500].rstrip()
        if label and is_clone_label(label) and self.config.speech.backend != "stub":
            if not runtime_status().installed:
                raise ConfigError(INSTALL_HINT)
            name = profile_name_from_label(label)
            names = [profile.name for profile in self.voice_profiles()]
            base = tuning or self.current_tuning()
            override = self._resolve_tuning(
                VoiceTuning(
                    voice=name,
                    rate=base.rate,
                    volume=base.volume,
                    pitch=base.pitch,
                    pause_ms=base.pause_ms,
                    emphasis=base.emphasis,
                ),
                names=names,
            )
            preview_settings = SpeechConfig(
                backend="clone",
                voice=override.voice,
                rate=override.rate,
                volume=override.volume,
                output_device=self.config.speech.output_device,
                pitch=override.pitch,
                pause_ms=override.pause_ms,
                emphasis=override.emphasis,
                voices_dir=str(self.voices_dir),
            )
            self._log_speech("preview", line, "spoken")
            preview_backend = self._backend_factory(preview_settings)
            if isinstance(preview_backend, CloneSpeechBackend):
                preview_backend.allow_live_synthesis()
            self.speech.preview_with(line, override, preview_backend)
            return line
        override = None if tuning is None else self._resolve_tuning(tuning)
        self._log_speech("preview", line, "spoken")
        self.speech.preview(line, override)
        return line

    def _store_tuning(self, applied: VoiceTuning) -> None:
        speech = self.config.speech
        speech.voice = applied.voice
        speech.rate = applied.rate
        speech.volume = applied.volume
        speech.pitch = applied.pitch
        speech.pause_ms = applied.pause_ms
        speech.emphasis = applied.emphasis

    def _install_backend(self) -> None:
        tuning = self.current_tuning()
        self.speech.apply_tuning(tuning)
        if self.config.speech.backend == "stub":
            return
        if not self._backend_matches():
            self.config.speech.voices_dir = str(self.voices_dir)
            backend = self._backend_factory(self.config.speech)
            self.speech.set_backend(backend)
            self.backend = backend
        if isinstance(self.backend, CloneSpeechBackend):
            self.backend.apply_tuning(tuning)
            self._prerender_clone(self.backend)

    def prerender_profile(self, name: str) -> None:
        """Render every stock line for a voice that was just built.

        Uses the current rate, pitch, pause, and emphasis. Does not switch
        the in-game backend. A later tuning change renders the lines again.
        """

        cleaned = name.strip()
        if not cleaned:
            return
        if (
            isinstance(self.backend, CloneSpeechBackend)
            and self.config.speech.backend == "clone"
            and self.config.speech.voice.strip().casefold() == cleaned.casefold()
        ):
            self._prerender_clone(self.backend)
            return
        if not runtime_status().installed:
            self._record(
                runtime_status().summary
                + " Until those packages are installed, this voice uses the Windows voice in a match."
            )
            return
        tuning = self.current_tuning()
        settings = SpeechConfig(
            backend="clone",
            voice=cleaned,
            rate=tuning.rate,
            volume=tuning.volume,
            output_device=self.config.speech.output_device,
            pitch=tuning.pitch,
            pause_ms=tuning.pause_ms,
            emphasis=tuning.emphasis,
            voices_dir=str(self.voices_dir),
        )
        backend = self._backend_factory(settings)
        if not isinstance(backend, CloneSpeechBackend):
            return
        self._renderers.append(backend)
        self._queue_prerender(
            backend,
            (
                f"Rendering every stock line for {cleaned}. "
                "Matches play those files only and do not synthesize live."
            ),
        )

    def poll_stock_lines(self) -> None:
        """Re-render the active cloned voice when ``lines.yaml`` changes."""

        stamp = self._stock_lines_stamp()
        if stamp is None:
            return
        previous = self._lines_stamp
        self._lines_stamp = stamp
        if previous is None or previous == stamp:
            return
        if isinstance(self.backend, CloneSpeechBackend) and self.config.speech.backend == "clone":
            self._record("Stock lines changed. Rendering them again for the cloned voice.")
            self._prerender_clone(self.backend)

    def _backend_matches(self) -> bool:
        current = self.speech.backend
        kind = self.config.speech.backend
        if kind == "clone":
            return isinstance(current, CloneSpeechBackend)
        if kind == "pyttsx3":
            return isinstance(current, Pyttsx3Backend)
        return True

    def _prerender_clone(self, backend: CloneSpeechBackend) -> None:
        status = runtime_status()
        if not status.installed:
            self._record(
                status.summary
                + " Missing stock lines will use the Windows voice until the clone is rendered."
            )
            return
        self._queue_prerender(
            backend,
            (
                "Rendering every stock line for the cloned voice. "
                "Matches play only those files, with no live synthesis."
            ),
        )

    def _queue_prerender(self, backend: CloneSpeechBackend, note: str) -> None:
        """Start a cache render, or hold it while the round phase is live."""

        live = self._round_phase_live()
        backend.set_round_live(live)
        backend.prerender(stock_line_texts(self.config.lines_path))
        if live:
            self._record("Rendering waits until this round ends.")
            return
        self._record(note)

    def _round_phase_live(self) -> bool:
        return (self._match_round or "").strip().lower() == "live"

    def _sync_render_pause(self) -> None:
        live = self._round_phase_live()
        if isinstance(self.backend, CloneSpeechBackend):
            self.backend.set_round_live(live)
        for backend in self._renderers:
            if isinstance(backend, CloneSpeechBackend):
                backend.set_round_live(live)

    def _note_optional_installs(self) -> None:
        """Remember optional requirement files that are already installed."""

        if self.config_path is None:
            return
        from suit_o.local_config import remember_installed_requirements
        from suit_o.update import detect_installed_requirements

        try:
            warning = remember_installed_requirements(
                self.config_path, detect_installed_requirements()
            )
        except OSError:
            logger.debug("Could not record installed optional requirements", exc_info=True)
            return
        if warning:
            self.note(warning)

    def _stock_lines_stamp(self) -> str | None:
        path = self.config.lines_path
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _resolve_tuning(self, tuning: VoiceTuning, *, names: list[str] | None = None) -> VoiceTuning:
        try:
            normalized = normalize_tuning(tuning)
            available = self.voice_names() if names is None else names
            voice = resolve_voice_name(normalized.voice, available if available else None)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        return VoiceTuning(
            voice=voice,
            rate=normalized.rate,
            volume=normalized.volume,
            pitch=normalized.pitch,
            pause_ms=normalized.pause_ms,
            emphasis=normalized.emphasis,
        )

    def match_is_live(self) -> bool:
        """True while a round is live. Menu, warmup, and time between matches are open."""

        from suit_o.chat.availability import chat_is_paused

        return chat_is_paused(self._match_activity, self._match_round, self._match_map_phase)

    def speak_chat(self, text: str) -> None:
        """Speak one chat sentence on the selected voice and output device.

        A live match does nothing. The line is not written to the event log,
        so a restart cannot leave a transcript on disk.
        """

        if self.match_is_live():
            return
        line = text.strip()
        if not line:
            return
        if len(line) > 500:
            line = line[:500].rstrip()
        if self.config.speech.backend == "clone" and self.config.speech.voice:
            self._speak_chat_clone(line)
            return
        self.speech.submit(
            Utterance(event_type="chat", text=line, priority=100),
            bypass_mute=True,
        )

    def interrupt_chat(self) -> None:
        """Stop chat audio without shutting down the speech thread."""

        self._chat_renderer.discard()
        self.speech.interrupt()

    def release_chat_voice(self) -> None:
        """Drop queued chat renders and unload the cloned-voice model.

        Chat keeps the model loaded between sentences. The chat tab calls this
        when it goes idle or a round goes live, so a match does not hold the GPU.
        """

        self._chat_renderer.discard()
        if self.config.speech.backend != "clone":
            return
        try:
            from suit_o.voice.engine import release_model
        except ImportError:
            return
        release_model()

    def _speak_chat_clone(self, line: str) -> None:
        from suit_o.voice.runtime import runtime_status

        if not runtime_status().installed:
            self.speech.submit(
                Utterance(event_type="chat", text=line, priority=100),
                bypass_mute=True,
            )
            return
        tuning = self.current_tuning()
        preview_settings = SpeechConfig(
            backend="clone",
            voice=self.config.speech.voice,
            rate=tuning.rate,
            volume=tuning.volume,
            output_device=self.config.speech.output_device,
            pitch=tuning.pitch,
            pause_ms=tuning.pause_ms,
            emphasis=tuning.emphasis,
            voices_dir=str(self.voices_dir),
        )
        preview_backend = self._backend_factory(preview_settings)
        if isinstance(preview_backend, CloneSpeechBackend):
            preview_backend.allow_live_synthesis()
            preview_backend.keep_model_loaded()
            preview_backend.use_rendered(self._chat_renderer.render(line, preview_backend.render_live))
        self.speech.preview_with(line, tuning, preview_backend)

    def test_voice(self, text: str | None = None) -> str:
        """Speak a line on the current device, even when Suit-O is muted."""

        line = (text or TEST_VOICE_LINE).strip()
        if not line:
            raise ValueError("Test voice needs a line to speak")
        self._log_speech("test", line, "spoken")
        self.speech.submit(
            Utterance(event_type="test", text=line, priority=100),
            bypass_mute=True,
        )
        return line

    def restart_blocked(self) -> bool:
        """A live round must finish before Suit-O restarts or pulls an update."""

        return restart_is_blocked(self._match_activity, self._match_round)

    def _note_match(self, snapshot) -> None:
        own = snapshot.own
        if own is not None and own.activity:
            self._match_activity = own.activity
        if snapshot.map_present:
            self._match_map_phase = snapshot.map_phase
        else:
            self._match_map_phase = None
        if snapshot.round_present and snapshot.round_phase:
            self._match_round = snapshot.round_phase
        elif not snapshot.round_present:
            self._match_round = None
        self._sync_render_pause()

    def lineup_view(self) -> DeckView:
        """Current overlay card. Safe to call from the window thread."""

        view = self.lineups.view()
        if not self.config.lineups.enabled:
            return DeckView(
                visible=False,
                reason="disabled",
                map_key=view.map_key,
                side=view.side,
                index=view.index,
                total=view.total,
                card=None,
                hidden=view.hidden,
            )
        return view

    def lineup_next(self) -> DeckView:
        return self.lineups.cycle(1)

    def lineup_previous(self) -> DeckView:
        return self.lineups.cycle(-1)

    def lineup_toggle(self) -> DeckView:
        view = self.lineups.toggle()
        self.note("Lineup overlay hidden" if view.hidden else "Lineup overlay will show with the grenade you are holding")
        return view

    def save_lineup_preferences(
        self,
        *,
        enabled: bool,
        width: int,
        opacity: float,
        corner: str,
        monitor: int,
        hotkey_next: str,
        hotkey_previous: str,
        hotkey_toggle: str,
        smokes_only: bool = True,
    ) -> None:
        """Store overlay size, corner, and hotkeys. Does not touch speech settings."""

        if self.config_path is None:
            raise RuntimeError("Suit-O has no config file to update")
        from suit_o.lineups.hotkeys import HotkeyError, canonical_hotkey

        try:
            next_key = canonical_hotkey(hotkey_next)
            previous_key = canonical_hotkey(hotkey_previous)
            toggle_key = canonical_hotkey(hotkey_toggle)
        except HotkeyError as exc:
            raise ConfigError(str(exc)) from exc
        store_personal_settings(
            self.config_path,
            enabled=enabled,
            width=width,
            opacity=opacity,
            corner=corner,
            monitor=monitor,
            hotkey_next=next_key,
            hotkey_previous=previous_key,
            hotkey_toggle=toggle_key,
            smokes_only=bool(smokes_only),
            voice_key=self.config.ptt.cs2_voice_key,
            ptt_key=self.config.ptt.keybind,
        )
        self._after_settings_saved()
        settings = self.config.lineups
        settings.enabled = enabled
        settings.width = width
        settings.opacity = round(float(opacity), 2)
        settings.corner = corner.strip().lower()
        settings.monitor = monitor
        settings.hotkey_next = next_key
        settings.hotkey_previous = previous_key
        settings.hotkey_toggle = toggle_key
        settings.smokes_only = bool(smokes_only)
        self.lineups.set_enabled(enabled)
        self.lineups.set_smokes_only(bool(smokes_only))

    def save_preferences(self) -> None:
        """Write volume, mute, output device, and voice tuning to config.local.yaml.

        ``config.yaml`` is left untouched. This stores the live settings, not
        an unsaved draft on the voice panel.
        """

        if self.config_path is None:
            raise RuntimeError("Suit-O has no config file to update")
        speech = self.config.speech
        store_personal_settings(
            self.config_path,
            volume=speech.volume,
            muted=self.muted,
            output_device=speech.output_device,
            voice=speech.voice,
            rate=speech.rate,
            pitch=speech.pitch,
            pause_ms=speech.pause_ms,
            emphasis=speech.emphasis,
            backend=speech.backend,
        )
        self._after_settings_saved()

    def save_menu_greeting(self, enabled: bool) -> None:
        """Remember whether the main menu asks about queueing Premier."""

        if self.config_path is None:
            raise RuntimeError("Suit-O has no config file to update")
        store_personal_settings(self.config_path, menu_greeting=bool(enabled))
        self.config.menu_greeting = bool(enabled)
        self._after_settings_saved()

    def save_chattiness(self, level: str) -> str:
        """Set how much Suit-O talks. Takes effect on the next event and chat reply."""

        from suit_o.lines.chattiness import ChattinessError, normalize_chattiness

        try:
            cleaned = normalize_chattiness(level)
        except ChattinessError as exc:
            raise ConfigError(str(exc)) from exc
        if self.config_path is not None:
            store_personal_settings(self.config_path, chattiness=cleaned)
        self.config.chattiness = cleaned
        if hasattr(self.lines, "set_chattiness"):
            self.lines.set_chattiness(cleaned)
        self._after_settings_saved()
        return cleaned

    def save_update_preference(self, check_on_launch: bool) -> None:
        """Remember whether the window should ``git pull`` when it opens."""

        if self.config_path is None:
            raise RuntimeError("Suit-O has no config file to update")
        store_personal_settings(self.config_path, check_on_launch=bool(check_on_launch))
        self.config.updates.check_on_launch = bool(check_on_launch)
        self._after_settings_saved()

    def reload_content(self) -> ReloadResult:
        """Apply config, lines, voices, and lineups. Keep the previous ones if invalid.

        A change to the listener address or token asks the window to restart,
        because the port is already bound.
        """

        if self.config_path is None:
            return ReloadResult(False, "Suit-O has no config file to reload")
        from suit_o.config import load_config

        try:
            loaded = load_config(self.config_path)
        except (ConfigError, OSError, ValueError, yaml.YAMLError) as exc:
            message = f"Kept the previous settings. {exc}"
            self.note(message)
            return ReloadResult(False, message)
        server = self.config.server
        if (
            loaded.server.host != server.host
            or loaded.server.port != server.port
            or loaded.server.token != server.token
        ):
            self.note("The listener address or token changed. Restarting.")
            return ReloadResult(True, "The listener address or token changed.", restart=True)
        try:
            provider = YamlLineProvider.from_file(
                loaded.lines_path,
                cooldowns=loaded.cooldowns,
                default_cooldown=loaded.default_cooldown,
                min_interval=loaded.min_interval,
                preempt_min_priority=loaded.preempt_min_priority,
                muted=loaded.mute,
                chattiness=loaded.chattiness,
            )
        except (OSError, ValueError, yaml.YAMLError) as exc:
            message = f"Kept the previous lines. {exc}"
            self.note(message)
            return ReloadResult(False, message)

        previous_config = self.config
        previous_lines = self.lines
        previous_detector = self.detector
        previous_tuning = self.current_tuning()
        previous_backend = previous_config.speech.backend
        previous_voice = previous_config.speech.voice
        loaded.speech.voices_dir = str(self.voices_dir)
        try:
            self.config = loaded
            if isinstance(self.lines, YamlLineProvider):
                provider.carry_clocks(self.lines)
            self.lines = provider
            self.detector.set_thresholds(loaded.thresholds)
            self.speech.preempt_min_priority = loaded.preempt_min_priority
            self.speech.set_muted(loaded.mute)
            self.speech.set_volume(loaded.speech.volume)
            self.speech.set_output_device(loaded.speech.output_device)
            self.speech.apply_tuning(self.current_tuning())
            self.lineups.set_enabled(loaded.lineups.enabled)
            self.lineups.set_smokes_only(loaded.lineups.smokes_only)
            tuning_changed = self.current_tuning() != previous_tuning
            backend_changed = (
                loaded.speech.backend != previous_backend or loaded.speech.voice != previous_voice
            )
            if backend_changed:
                self._install_backend()
            elif tuning_changed and isinstance(self.backend, CloneSpeechBackend):
                self._prerender_clone(self.backend)
            self.poll_stock_lines()
        except (ConfigError, OSError, ValueError) as exc:
            self.config = previous_config
            self.lines = previous_lines
            self.detector = previous_detector
            message = f"Kept the previous settings. {exc}"
            self.note(message)
            return ReloadResult(False, message)
        self.note("Reloaded settings.")
        return ReloadResult(True, "Reloaded settings.", applied=True)

    def _after_settings_saved(self) -> None:
        hook = self._on_settings_saved
        if hook is not None:
            hook()

    def activity(self) -> tuple[Activity, ...]:
        with self._activity_lock:
            return tuple(self._activity)

    def restore_activity(self, entries: Sequence[tuple[float, str]]) -> None:
        """Put carried log lines back. Their times stay. The token stays out."""

        token = self.config.server.token.strip()
        with self._activity_lock:
            for at, message in entries:
                text = message
                if token:
                    text = text.replace(token, "[redacted]")
                self._activity_seq += 1
                self._activity.append(Activity(self._activity_seq, float(at), text))

    def snapshot(self) -> ListenerSnapshot:
        listening = self._started and not self._did_stop and self._httpd is not None
        host = self.config.server.host
        port = self.config.server.port
        if self._httpd is not None:
            try:
                host, port = self.server_address
            except RuntimeError:
                listening = False
        last = self.last_payload_at
        seconds = None if last is None else max(0.0, time.time() - last)
        return ListenerSnapshot(
            listening=listening,
            host=host,
            port=port,
            muted=self.muted,
            volume=float(self.config.speech.volume),
            output_device=self.config.speech.output_device,
            received=self.processed,
            spoken=len(self.speech.history),
            seconds_since_payload=seconds,
            activity=self.activity(),
        )

    def status(self) -> dict:
        shot = self.snapshot()
        return {
            "muted": shot.muted,
            "received": shot.received,
            "spoken": shot.spoken,
            "listening": shot.listening,
            "volume": shot.volume,
            "output_device": shot.output_device,
            "last_payload_at": self.last_payload_at,
            "seconds_since_payload": shot.seconds_since_payload,
        }

    def stop(self) -> None:
        if self._did_stop:
            return
        self._did_stop = True
        self._stop.set()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        if self._worker is not None:
            self._worker.join(timeout=2)
        self._chat_renderer.close()
        self.speech.stop()
        if self._http_thread is not None:
            self._http_thread.join(timeout=2)
        for renderer in self._renderers:
            renderer.close()
        self._renderers.clear()

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._lines_checked >= 1:
                self._lines_checked = now
                try:
                    self.poll_stock_lines()
                except Exception:
                    logger.exception("Could not check the stock lines file")
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if item is None:
                break
            self.last_payload_at = time.time()
            try:
                self._handle(item)
            except Exception:
                logger.exception("Failed to handle a GSI payload")
            finally:
                self.processed += 1

    def _handle(self, data: dict) -> None:
        snapshot = parse_payload(data)
        if snapshot is None:
            return
        self.lineups.observe(snapshot)
        self._note_match(snapshot)
        detected = self.detector.update(snapshot)
        now = float(self._clock())
        events = [
            GameEvent(item.type, self.config.priority_for(item.type), dict(item.context))
            for item in detected
        ]
        events.sort(key=lambda event: -event.priority)
        for event in events:
            if event.type == EventType.MENU_GREETING and not self.config.menu_greeting:
                self._log_speech(event.type.value, "", "disabled")
                continue
            decision = self.lines.decide(event, now)
            if decision.status == "spoken" and decision.text:
                self._log_speech(event.type.value, decision.text, "spoken")
                self.speech.submit(
                    Utterance(event_type=event.type.value, text=decision.text, priority=event.priority),
                    max_age=GAME_LINE_MAX_AGE,
                )
            else:
                self._log_speech(event.type.value, "", decision.status)

    def _stdin_loop(self) -> None:
        host, port = self.server_address
        print(
            f"Suit-O is listening on http://{host}:{port}. "
            "Type m and press Enter to mute or unmute. Type q and press Enter to quit.",
            flush=True,
        )
        try:
            for line in sys.stdin:
                command = line.strip().lower()
                if command == "m":
                    muted = self.toggle_mute()
                    print("Muted." if muted else "Listening.", flush=True)
                elif command == "q":
                    self.stop()
                    return
        except Exception:
            logger.debug("Console input ended", exc_info=True)

    def note(self, message: str) -> None:
        """Append one line to the desktop log."""

        self._record(message)

    def _on_gsi_rejected(self, reason: str) -> None:
        self._record(f"gsi: rejected ({reason})")

    def _on_speech_dropped(self, utterance: Utterance) -> None:
        self._log_speech(utterance.event_type, utterance.text, "queue full")

    def _on_speech_stale(self, utterance: Utterance) -> None:
        self._log_speech(utterance.event_type, utterance.text, "too late")

    def _log_speech(self, event: str, text: str, status: str) -> None:
        """Show a spoken line, or why a detected event was not spoken."""

        if status == "spoken":
            self._record(f"{event}: {text}")
        else:
            self._record(f"{event}: skipped ({status})")

    def _record(self, message: str) -> None:
        token = self.config.server.token.strip()
        if token:
            message = message.replace(token, "[redacted]")
        with self._activity_lock:
            self._activity_seq += 1
            self._activity.append(Activity(self._activity_seq, time.time(), message))
        logger.info("%s", message)
