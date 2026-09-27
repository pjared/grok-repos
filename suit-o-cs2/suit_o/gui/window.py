"""tkinter window. It paints snapshots and forwards clicks to SuitOApp.

Nothing in this module decides which device is legal, which voice exists, or
when a line may play. That stays in the core so it can be tested without a
display.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import tkinter as tk
from tkinter import messagebox, ttk

from suit_o.app import SuitOApp
from suit_o.config import ConfigError
from suit_o.gui.status import (
    device_menu_labels,
    format_activity,
    format_game_state,
    format_listener,
    format_sound,
    selected_device_label,
    tone_color,
)
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

        self.root = tk.Tk()
        self.root.title("Suit-O")
        self.root.geometry("700x680")
        self.root.minsize(560, 520)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=(16, 12, 16, 12))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="Suit-O", font=("TkDefaultFont", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(frame, text="Local CS2 companion").grid(row=1, column=0, sticky="w", pady=(0, 8))

        self.notebook = ttk.Notebook(frame)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        listener = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        voice = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        self.notebook.add(listener, text="Listener")
        self.notebook.add(voice, text="Voice")
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
        self._paint_volume_caption(app.config.speech.volume)
        self._ui_ready = True

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
        ttk.Label(buttons, text="Recent events").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(10, 4)
        )

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
        self._refresh()
        self.root.mainloop()

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
            self._paint(self.app.snapshot())
        except Exception:
            logger.exception("Could not refresh the Suit-O window")
        self.root.after(400, self._refresh)

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

    def _set_status(self, dot: tk.Label, label: ttk.Label, text: str, tone: str) -> None:
        color = tone_color(tone)
        dot.configure(fg=color)
        label.configure(text=text)

    def _paint_volume_caption(self, volume: float) -> None:
        self.volume_caption.configure(text=f"{int(round(volume * 100))}%")
        panel = getattr(self, "voice_panel", None)
        if panel is not None:
            panel.paint_volume(volume)

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
