"""tkinter window. It paints snapshots and forwards clicks to SuitOApp.

Nothing in this module decides which device is legal, which voice exists, or
when a line may play. That stays in the core so it can be tested without a
display.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from contextlib import contextmanager

import tkinter as tk
from tkinter import messagebox, ttk

from suit_o.app import SuitOApp
from suit_o.config import PROJECT_ROOT, ConfigError
from suit_o.local_config import local_config_path
from suit_o.reload import (
    FileWatcher,
    RestartState,
    choose_reload,
    consume_restart_state,
    gui_restart_argv,
    write_activity_handoff,
    write_restart_state,
)
from suit_o.update import install_requirements, run_git_update
from suit_o.gui.status import (
    device_menu_labels,
    format_activity,
    format_game_state,
    format_listener,
    format_sound,
    selected_device_label,
    tone_color,
)
from suit_o.gui.drops import desktop_root
from suit_o.gui.global_hotkeys import GlobalHotkeys
from suit_o.gui.chat import ChatPanel
from suit_o.gui.clips import ClipsPanel
from suit_o.gui.lineups import LineupsPanel
from suit_o.gui.overlay import LineupOverlay, monitors_for
from suit_o.gui.training import TrainingPanel
from suit_o.gui.voice import VoicePanel
from suit_o.preferences import clamp_volume
from suit_o.speech.devices import WINDOWS_DEFAULT_LABEL

logger = logging.getLogger(__name__)


class SuitOWindow:
    def __init__(self, app: SuitOApp) -> None:
        self.app = app
        self._closed = False
        self._ui_ready = False
        self._dragging_volume = False
        self._syncing_volume = False
        self._save_job: str | None = None
        self._save_error_shown = False
        self._last_activity_seq = 0
        self._device_names: list[str] = []
        self._updating = False
        self._notice_job: str | None = None
        self._pending_update = False
        self._pending_restart = False
        self._pending_notice = "Reloaded"
        self._pending_noted = False
        config_path = app.config_path or (PROJECT_ROOT / "config.yaml")
        self._watcher = FileWatcher(
            PROJECT_ROOT,
            config_path=config_path,
            lines_path=app.config.lines_path,
        )
        app._on_settings_saved = self._ignore_own_save

        self.root = desktop_root()
        self.root.title("Suit-O")
        self.root.geometry("860x900")
        self.root.minsize(720, 760)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=(16, 12, 16, 12))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Suit-O", font=("TkDefaultFont", 16, "bold")).pack(side="left")
        self.notice = ttk.Label(header, text="", foreground="#0b6e4f")
        self.notice.pack(side="left", padx=(12, 0))
        ttk.Label(frame, text="Local CS2 companion").grid(row=1, column=0, sticky="w", pady=(0, 8))

        self.notebook = ttk.Notebook(frame)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        listener = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        voice = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        training = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        lineups = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        chat = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        self.notebook.add(listener, text="Listener")
        self.notebook.add(voice, text="Voice")
        self.notebook.add(training, text="Voice Training")
        self.notebook.add(lineups, text="Lineups")
        self.notebook.add(chat, text="Chat")
        chat.columnconfigure(0, weight=1)
        chat.rowconfigure(1, weight=1)
        training.columnconfigure(0, weight=1)
        training.rowconfigure(0, weight=1)
        training_book = ttk.Notebook(training)
        training_book.grid(row=0, column=0, sticky="nsew")
        script = ttk.Frame(training_book, padding=(4, 8, 4, 4))
        clips = ttk.Frame(training_book, padding=(4, 8, 4, 4))
        training_book.add(script, text="Script")
        training_book.add(clips, text="Clips")
        self.training_book = training_book
        self._clips_tab = clips
        script.columnconfigure(0, weight=1)
        clips.columnconfigure(0, weight=1)
        clips.rowconfigure(0, weight=1)
        self._build_listener(listener)

        self.volume = tk.DoubleVar(value=round(app.config.speech.volume * 100))
        self.scale.configure(variable=self.volume, command=self._on_volume)
        self.voice_panel = VoicePanel(
            voice,
            app,
            volume=self.volume,
            on_volume=self._on_volume,
            on_volume_press=self._volume_press,
            on_volume_release=self._volume_release,
            hold_updates=self._hold_volume,
            paint_volume=self._paint_volume_caption,
        )
        self.training_panel = TrainingPanel(
            script,
            app,
            on_profile_built=self._on_profile_built,
            schedule=lambda callback: self.root.after(0, callback),
            on_long_file=self._open_long_recording,
        )
        self.clips_panel = ClipsPanel(
            clips,
            app,
            schedule=lambda callback: self.root.after(0, callback),
        )
        self.lineups_panel = LineupsPanel(lineups, app, on_saved=self._bind_lineup_hotkeys)
        self.chat_panel = ChatPanel(
            chat,
            app,
            schedule=lambda callback: self.root.after(0, callback),
        )
        self.overlay: LineupOverlay | None = None
        self.hotkeys = GlobalHotkeys()
        self._paint_volume_caption(app.config.speech.volume)
        self._ui_ready = True

    def _open_long_recording(self, path) -> None:
        """A recording of 30 seconds or more is cut on the Clips page."""

        name = self.training_panel.name.get().strip() or "Suit-O"
        self.clips_panel.voice.set(name)
        self.clips_panel.reload_library()
        self.training_book.select(self._clips_tab)
        self.clips_panel.load_file(path)

    def _on_profile_built(self, name: str) -> None:
        self.voice_panel.reload_voices()
        self._record_profile(name)
        self.app.prerender_profile(name)

    def _record_profile(self, name: str) -> None:
        self.app.note(f"Cloned voice saved: {name}")
        self._paint(self.app.snapshot())

    def _build_listener(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)

        self.listener_dot = tk.Label(frame, text="●", font=("TkDefaultFont", 12))
        self.listener_dot.grid(row=2, column=0, sticky="w")
        self.listener_text = ttk.Label(frame)
        self.listener_text.grid(row=2, column=1, columnspan=2, sticky="w")

        self.game_dot = tk.Label(frame, text="●", font=("TkDefaultFont", 12))
        self.game_dot.grid(row=3, column=0, sticky="w")
        self.game_text = ttk.Label(frame)
        self.game_text.grid(row=3, column=1, columnspan=2, sticky="w")

        self.sound_dot = tk.Label(frame, text="●", font=("TkDefaultFont", 12))
        self.sound_dot.grid(row=4, column=0, sticky="w", pady=(0, 8))
        self.sound_text = ttk.Label(frame)
        self.sound_text.grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 8))

        controls = ttk.Frame(frame)
        controls.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        controls.columnconfigure(2, weight=1)
        self.mute_button = ttk.Button(controls, text="Mute", width=12, command=self._toggle_mute)
        self.mute_button.grid(row=0, column=0, sticky="w")
        ttk.Label(controls, text="Volume").grid(row=0, column=1, sticky="e", padx=(16, 8))
        self.scale = ttk.Scale(controls, from_=0, to=100, orient="horizontal")
        self.scale.grid(row=0, column=2, sticky="ew")
        self.scale.bind("<ButtonPress-1>", self._volume_press)
        self.scale.bind("<ButtonRelease-1>", self._volume_release)
        self.volume_caption = ttk.Label(controls, width=5, anchor="e")
        self.volume_caption.grid(row=0, column=3, padx=(8, 0))

        device_row = ttk.Frame(frame)
        device_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        device_row.columnconfigure(1, weight=1)
        ttk.Label(device_row, text="Output").grid(row=0, column=0, sticky="w")
        self.device = ttk.Combobox(device_row, state="readonly", width=64)
        self.device.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.device.bind("<<ComboboxSelected>>", self._on_device)
        ttk.Label(
            frame,
            text="Playback devices only. Microphones and virtual cables are not listed.",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 8))

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=3, sticky="new")
        ttk.Button(buttons, text="Test voice", command=self._test_voice).grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Refresh devices", command=self._reload_devices).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        self.update_button = ttk.Button(buttons, text="Update", command=self._update)
        self.update_button.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.update_status = ttk.Label(buttons, text="")
        self.update_status.grid(row=0, column=3, sticky="w", padx=(8, 0))
        self.menu_greeting = tk.BooleanVar(value=self.app.config.menu_greeting)
        ttk.Checkbutton(
            buttons,
            text="Greet me in the main menu",
            variable=self.menu_greeting,
            command=self._save_menu_greeting,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.check_updates = tk.BooleanVar(value=self.app.config.updates.check_on_launch)
        ttk.Checkbutton(
            buttons,
            text="Check for updates when Suit-O opens",
            variable=self.check_updates,
            command=self._save_update_pref,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))
        log_tools = ttk.Frame(buttons)
        log_tools.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 4))
        ttk.Label(log_tools, text="Recent events").pack(side="left")
        ttk.Button(log_tools, text="Copy", command=self._copy_log).pack(side="right")

        log_frame = ttk.Frame(frame)
        log_frame.grid(row=9, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled",
            relief="solid",
            borderwidth=1,
            bg="#ffffff",
            fg="#1a1a1a",
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.bind("<MouseWheel>", self._on_mousewheel)
        self.log.bind("<Button-4>", lambda _event: self.log.yview_scroll(-1, "units"))
        self.log.bind("<Button-5>", lambda _event: self.log.yview_scroll(1, "units"))

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._reload_devices()
        self.lineups_panel.set_monitors([item.label for item in monitors_for(self.root)])
        self.overlay = LineupOverlay(self.root, self.app, lambda: monitors_for(self.root))
        self._bind_lineup_hotkeys()
        self._restore_restart_state()
        self._refresh()
        if self.app.config.updates.check_on_launch:
            self._update()
        self.root.mainloop()

    def _bind_lineup_hotkeys(self) -> None:
        settings = self.app.config.lineups
        bindings = {}
        if settings.hotkey_next:
            bindings[settings.hotkey_next] = self.app.lineup_next
        if settings.hotkey_previous:
            bindings[settings.hotkey_previous] = self.app.lineup_previous
        if settings.hotkey_toggle:
            bindings[settings.hotkey_toggle] = self.app.lineup_toggle
        self.hotkeys.start(bindings)

    def _on_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
            self._save_job = None
        try:
            self.app.save_preferences()
        except Exception as exc:
            logger.exception("Could not save Suit-O settings")
            messagebox.showerror("Suit-O", f"Could not save settings.\n{exc}")
        self.hotkeys.stop()
        if self.overlay is not None:
            self.overlay.close()
        self.app.stop()
        self.root.destroy()

    def _toggle_mute(self) -> None:
        self.app.toggle_mute()
        self._save()
        self._paint(self.app.snapshot())

    def _volume_press(self, _event: object) -> None:
        self._dragging_volume = True

    def _volume_release(self, _event: object) -> None:
        self._dragging_volume = False
        self._save()

    def _on_volume(self, value: str) -> None:
        if not self._ui_ready or self._closed or self._syncing_volume:
            return
        try:
            volume = clamp_volume(float(value) / 100.0)
        except (ConfigError, ValueError):
            return
        self._paint_volume_caption(volume)
        if abs(volume - float(self.app.config.speech.volume)) < 0.005:
            return
        try:
            self.app.set_volume(volume)
        except ConfigError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self._schedule_save()

    def _schedule_save(self) -> None:
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, self._save)

    def _save(self) -> None:
        self._save_job = None
        if self._closed:
            return
        try:
            self.app.save_preferences()
        except Exception as exc:
            logger.exception("Could not save Suit-O settings")
            if not self._save_error_shown:
                self._save_error_shown = True
                messagebox.showerror("Suit-O", f"Could not save settings.\n{exc}")
            return
        self._save_error_shown = False

    def _on_device(self, _event: object = None) -> None:
        label = self.device.get()
        query = "" if label == WINDOWS_DEFAULT_LABEL else label
        try:
            self.app.set_output_device(query)
            self.app.save_preferences()
        except Exception as exc:
            messagebox.showerror("Suit-O", str(exc))
            self._reload_devices()
            return
        self._paint(self.app.snapshot())

    def _test_voice(self) -> None:
        try:
            self.app.test_voice()
        except Exception as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self._paint(self.app.snapshot())

    def _reload_devices(self) -> None:
        self._device_names = self.app.output_device_names()
        current = self.app.config.speech.output_device
        self.device["values"] = device_menu_labels(self._device_names, current)
        self.device.set(selected_device_label(current, self._device_names))

    def _refresh(self) -> None:
        if self._closed:
            return
        try:
            self._release_pending()
            if self._closed:
                return
            self._poll_watcher()
            if self._closed:
                return
            self.app.poll_stock_lines()
            self._paint(self.app.snapshot())
        except Exception:
            logger.exception("Could not refresh the Suit-O window")
        if not self._closed:
            self.root.after(400, self._refresh)

    def _ignore_own_save(self) -> None:
        if self.app.config_path is None:
            return
        self._watcher.ignore(local_config_path(self.app.config_path), time.monotonic() + 2.0)

    def _poll_watcher(self) -> None:
        kinds = self._watcher.scan(time.monotonic())
        if not kinds:
            return
        action = choose_reload(kinds)
        if action == "restart" and self.app.restart_blocked():
            if "content" in kinds:
                self._apply_content_reload()
            self._defer("restart", "Reloaded")
            return
        if action == "restart":
            self._restart_in_place("Reloaded")
            return
        if action != "reload":
            return
        self._apply_content_reload()

    def _apply_content_reload(self) -> None:
        """Apply config and content now. A listener-address change waits out a live round."""

        result = self.app.reload_content()
        if result.restart:
            self._restart_or_defer("Reloaded")
            return
        if not result.applied:
            return
        self._reload_devices()
        self.voice_panel.show(self.app.current_tuning())
        self.lineups_panel.sync_from_app()
        self.lineups_panel.reload()
        self._bind_lineup_hotkeys()
        self.check_updates.set(self.app.config.updates.check_on_launch)
        self.menu_greeting.set(self.app.config.menu_greeting)
        self._show_notice("Reloaded")

    def _restore_restart_state(self) -> None:
        if self.app.config_path is None:
            return
        state = consume_restart_state(self.app.config_path)
        if state is None:
            return
        self.root.geometry(f"{state.width}x{state.height}{state.x:+d}{state.y:+d}")
        try:
            self.notebook.select(state.tab)
        except tk.TclError:
            logger.debug("Could not restore the notebook tab", exc_info=True)
        notice = state.notice or "Reloaded"
        self._show_notice(notice)
        self.app.note(notice)

    def _restart_or_defer(self, notice: str) -> None:
        if self.app.restart_blocked():
            self._defer("restart", notice)
            return
        self._restart_in_place(notice)

    def _defer(self, kind: str, notice: str = "Reloaded") -> None:
        """Hold a process restart or Update until the live round ends.

        An Update covers a code restart, so a waiting pull replaces a waiting
        restart. A restart requested after the pull has already landed stays
        queued beside it.
        """

        if kind == "update":
            self._pending_update = True
        else:
            self._pending_restart = True
            self._pending_notice = notice
        self.notice.configure(text="Update pending")
        if self._notice_job is not None:
            self.root.after_cancel(self._notice_job)
            self._notice_job = None
        detail = (
            "Update pending. Suit-O will reload when you leave the live round "
            "or return to the menu."
        )
        self.update_status.configure(text=detail)
        if not self._pending_noted:
            self.app.note(detail)
            self._pending_noted = True

    def _release_pending(self) -> None:
        if self._closed or self._updating:
            return
        if self.app.restart_blocked():
            return
        if not self._pending_update and not self._pending_restart:
            return
        if self._pending_update:
            self._pending_update = False
            self._pending_noted = self._pending_restart
            self._update()
            return
        notice = self._pending_notice
        self._pending_restart = False
        self._pending_noted = False
        self._restart_in_place(notice)

    def _show_notice(self, text: str) -> None:
        self.notice.configure(text=text)
        if self._notice_job is not None:
            self.root.after_cancel(self._notice_job)
        self._notice_job = self.root.after(4000, self._clear_notice)

    def _clear_notice(self) -> None:
        self._notice_job = None
        if self._closed:
            return
        if self._pending_update or self._pending_restart:
            self.notice.configure(text="Update pending")
            return
        self.notice.configure(text="")

    def _save_menu_greeting(self) -> None:
        try:
            self.app.save_menu_greeting(bool(self.menu_greeting.get()))
        except Exception as exc:
            messagebox.showerror("Suit-O", str(exc))

    def _save_update_pref(self) -> None:
        try:
            self.app.save_update_preference(bool(self.check_updates.get()))
        except Exception as exc:
            messagebox.showerror("Suit-O", str(exc))

    def _update(self) -> None:
        if self._updating or self._closed:
            return
        if self.app.restart_blocked():
            self._defer("update")
            return
        self._updating = True
        self.update_button.state(["disabled"])
        self.update_status.configure(text="Checking for updates...")
        threading.Thread(target=self._update_worker, name="suit-o-update", daemon=True).start()

    def _update_worker(self) -> None:
        try:
            outcome = run_git_update(PROJECT_ROOT)
            pip_error = None
            if outcome.ok and outcome.changed and outcome.requirements:
                pip_error = install_requirements(outcome.requirements)
        except Exception as exc:
            outcome = None
            pip_error = f"Update failed. {exc}"
        if self._closed:
            return
        self.root.after(0, lambda: self._finish_update(outcome, pip_error))

    def _finish_update(self, outcome, pip_error: str | None) -> None:
        self._updating = False
        if self._closed:
            return
        self.update_button.state(["!disabled"])
        if pip_error:
            self.update_status.configure(text=pip_error)
            self.app.note(pip_error)
            return
        if outcome is None:
            return
        self.update_status.configure(text=outcome.message)
        self.app.note(outcome.message)
        if outcome.ok and outcome.changed:
            self._restart_or_defer("Reloaded")

    def _restart_in_place(self, notice: str) -> None:
        """Stop the listener, free its port, and replace this process."""

        if self._closed:
            return
        try:
            self.app.save_preferences()
        except Exception as exc:
            logger.exception("Could not save Suit-O settings before reload")
            messagebox.showerror("Suit-O", f"Could not save settings.\n{exc}")
            return
        self._closed = True
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
            self._save_job = None
        if self.app.config_path is not None:
            width, height, x, y = _parse_geometry(self.root.geometry())
            try:
                tab = int(self.notebook.index(self.notebook.select()))
            except tk.TclError:
                tab = 0
            write_restart_state(
                self.app.config_path,
                RestartState(x=x, y=y, width=width, height=height, tab=tab, notice=notice),
            )
        write_activity_handoff(
            [(entry.at, entry.message) for entry in self.app.activity()],
            secret=self.app.config.server.token,
        )
        self.hotkeys.stop()
        if self.overlay is not None:
            self.overlay.close()
        self.app.stop()
        argv = gui_restart_argv(self.app.config_path)
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        try:
            os.execv(sys.executable, argv)
        except OSError as exc:
            logger.exception("Could not relaunch Suit-O")
            _report_relaunch_failure(str(exc))

    def _paint(self, shot) -> None:
        listener, listener_tone = format_listener(shot.listening, shot.host, shot.port)
        self._set_status(self.listener_dot, self.listener_text, listener, listener_tone)
        game, game_tone = format_game_state(shot.seconds_since_payload, received=shot.received)
        self._set_status(self.game_dot, self.game_text, game, game_tone)
        sound, sound_tone = format_sound(shot.muted)
        self._set_status(self.sound_dot, self.sound_text, sound, sound_tone)
        self.mute_button.configure(text="Unmute" if shot.muted else "Mute")
        if not self._dragging_volume:
            percent = round(shot.volume * 100)
            if abs(float(self.volume.get()) - percent) >= 1:
                with self._hold_volume():
                    self.volume.set(percent)
                self._paint_volume_caption(shot.volume)
        self._append_activity(shot.activity)
        chat_panel = getattr(self, "chat_panel", None)
        if chat_panel is not None:
            chat_panel.sync_paused(self.app.match_is_live())
            chat_panel.poll_idle()

    def _set_status(self, dot: tk.Label, label: ttk.Label, text: str, tone: str) -> None:
        color = tone_color(tone)
        dot.configure(fg=color)
        label.configure(text=text)

    def _paint_volume_caption(self, volume: float) -> None:
        self.volume_caption.configure(text=f"{int(round(volume * 100))}%")
        panel = getattr(self, "voice_panel", None)
        if panel is not None:
            panel.paint_volume(volume)

    def _copy_log(self) -> None:
        text = self.log.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._show_notice("Copied")

    def _append_activity(self, entries: tuple) -> None:
        fresh = [entry for entry in entries if entry.seq > self._last_activity_seq]
        if not fresh:
            return
        stick = self._log_is_at_bottom()
        self.log.configure(state="normal")
        for entry in fresh:
            self.log.insert("end", format_activity(entry) + "\n")
            self._last_activity_seq = entry.seq
        self.log.configure(state="disabled")
        if stick:
            self.log.see("end")

    def _log_is_at_bottom(self) -> bool:
        _first, last = self.log.yview()
        return last > 0.98

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = getattr(event, "delta", 0)
        if not delta:
            return
        self.log.yview_scroll(int(-delta / 120) or (-1 if delta > 0 else 1), "units")

    @contextmanager
    def _hold_volume(self):
        self._syncing_volume = True
        try:
            yield
        finally:
            self._syncing_volume = False


def _parse_geometry(spec: str) -> tuple[int, int, int, int]:
    match = re.match(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", spec)
    if match is None:
        return (860, 900, 0, 0)
    width, height, x, y = match.groups()
    return (int(width), int(height), int(x), int(y))


def _report_relaunch_failure(message: str) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Suit-O", f"Suit-O could not reload.\n{message}")
        root.destroy()
    except Exception:
        logger.error("Suit-O could not reload: %s", message)
