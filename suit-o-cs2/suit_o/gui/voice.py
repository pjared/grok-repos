"""Voice tab. It edits a draft and asks SuitOApp to preview, save, or reset.

Rate, pitch, pause, and emphasis stay on the widgets until Save or Reset.
Volume is the same control as the Listener tab and is saved as it moves.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from suit_o.app import SuitOApp
from suit_o.config import ConfigError
from suit_o.preferences import clamp_volume
from suit_o.voice.profile import is_clone_label, profile_name_from_label
from suit_o.speech.tuning import (
    DEFAULT_PREVIEW_LINE,
    ENGINE_DEFAULT_VOICE,
    PAUSE_MAX,
    PAUSE_MIN,
    PITCH_MAX,
    PITCH_MIN,
    RATE_MAX,
    RATE_MIN,
    VoiceTuning,
    emphasis_from_label,
    emphasis_label,
    selected_voice_label,
    voice_menu_labels,
)


class VoicePanel:
    def __init__(
        self,
        parent: ttk.Frame,
        app: SuitOApp,
        *,
        volume: tk.DoubleVar,
        on_volume: Callable[[str], None],
        on_volume_press: Callable[[object], None],
        on_volume_release: Callable[[object], None],
        hold_updates: Callable[[], object],
        paint_volume: Callable[[float], None] | None = None,
    ) -> None:
        self.app = app
        self.volume = volume
        self._hold_updates = hold_updates
        self._paint_shared_volume = paint_volume
        self._voice_names: list[str] = []

        parent.columnconfigure(1, weight=1)
        hint = (
            "Save applies the voice, rate, pitch, pause, and emphasis to every "
            "in-game line. A voice built on the Voice Training tab shows up here "
            "as Clone: name. Preview speaks the text below with the sliders as they "
            "are now, through the output device on the Listener tab, and does not "
            "change those saved settings. Volume is shared with the Listener tab."
        )
        ttk.Label(parent, text=hint, wraplength=640, justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )

        ttk.Label(parent, text="Voice").grid(row=1, column=0, sticky="w")
        self.voice = ttk.Combobox(parent, state="readonly", width=48)
        self.voice.grid(row=1, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(parent, text="Refresh voices", command=self.reload_voices).grid(
            row=1, column=2, sticky="e"
        )

        self.rate = tk.DoubleVar(value=app.config.speech.rate)
        self.rate_caption = ttk.Label(parent, width=10, anchor="e")
        self._slider(
            parent,
            row=2,
            label="Rate",
            variable=self.rate,
            from_=RATE_MIN,
            to=RATE_MAX,
            command=self._on_rate,
            caption=self.rate_caption,
        )

        self.pitch = tk.DoubleVar(value=app.config.speech.pitch)
        self.pitch_caption = ttk.Label(parent, width=10, anchor="e")
        self._slider(
            parent,
            row=3,
            label="Pitch",
            variable=self.pitch,
            from_=PITCH_MIN,
            to=PITCH_MAX,
            command=self._on_pitch,
            caption=self.pitch_caption,
        )

        self.volume_caption = ttk.Label(parent, width=10, anchor="e")
        scale = self._slider(
            parent,
            row=4,
            label="Volume",
            variable=self.volume,
            from_=0,
            to=100,
            command=on_volume,
            caption=self.volume_caption,
        )
        scale.bind("<ButtonPress-1>", on_volume_press)
        scale.bind("<ButtonRelease-1>", on_volume_release)

        self.pause = tk.DoubleVar(value=app.config.speech.pause_ms)
        self.pause_caption = ttk.Label(parent, width=10, anchor="e")
        self._slider(
            parent,
            row=5,
            label="Pause",
            variable=self.pause,
            from_=PAUSE_MIN,
            to=PAUSE_MAX,
            command=self._on_pause,
            caption=self.pause_caption,
        )

        ttk.Label(parent, text="Emphasis").grid(row=6, column=0, sticky="w", pady=(8, 0))
        self.emphasis = ttk.Combobox(
            parent,
            state="readonly",
            width=16,
            values=("None", "Mild", "Strong"),
        )
        self.emphasis.grid(row=6, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(parent, text="Preview").grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.preview_text = tk.Text(
            parent,
            height=4,
            wrap="word",
            relief="solid",
            borderwidth=1,
            bg="#ffffff",
            fg="#1a1a1a",
        )
        self.preview_text.grid(row=8, column=0, columnspan=3, sticky="ew")
        self.preview_text.insert("1.0", DEFAULT_PREVIEW_LINE)

        buttons = ttk.Frame(parent)
        buttons.grid(row=9, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.preview_button = ttk.Button(buttons, text="Preview", command=self.preview)
        self.preview_button.grid(row=0, column=0, sticky="w")
        self.save_button = ttk.Button(buttons, text="Save", command=self.save)
        self.save_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.reset_button = ttk.Button(buttons, text="Reset to defaults", command=self.reset)
        self.reset_button.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.show(app.current_tuning())
        self.reload_voices()

    def show(self, tuning: VoiceTuning) -> None:
        """Paint ``tuning`` into the draft controls."""

        self.reload_voices()
        if tuning.voice == self.app.config.speech.voice:
            self.voice.set(self.app.current_voice_label())
        else:
            self.voice.set(selected_voice_label(tuning.voice, self._voice_names))
        self.rate.set(tuning.rate)
        self.pitch.set(tuning.pitch)
        self.pause.set(tuning.pause_ms)
        self.emphasis.set(emphasis_label(tuning.emphasis))
        self._on_rate(str(tuning.rate))
        self._on_pitch(str(tuning.pitch))
        self._on_pause(str(tuning.pause_ms))
        with self._hold_updates():
            self.volume.set(round(tuning.volume * 100))
        self.paint_volume(tuning.volume)
        if self._paint_shared_volume is not None:
            self._paint_shared_volume(tuning.volume)

    def paint_volume(self, volume: float) -> None:
        self.volume_caption.configure(text=f"{int(round(volume * 100))}%")

    def reload_voices(self) -> None:
        self._voice_names = self.app.voice_names()
        current = self.voice.get().strip() or self.app.current_voice_label()
        labels = self.app.voice_picker_labels()
        if current and current not in labels:
            labels.append(current)
        self.voice["values"] = labels
        if current in labels:
            self.voice.set(current)
        else:
            self.voice.set(self.app.current_voice_label())

    def draft(self) -> VoiceTuning:
        return VoiceTuning(
            voice=self._selected_voice(),
            rate=int(round(float(self.rate.get()))),
            volume=clamp_volume(float(self.volume.get()) / 100.0),
            pitch=int(round(float(self.pitch.get()))),
            pause_ms=int(round(float(self.pause.get()))),
            emphasis=emphasis_from_label(self.emphasis.get() or "None"),
        )

    def preview(self) -> None:
        try:
            self.app.preview_voice(
                self.preview_text.get("1.0", "end"),
                self.draft(),
                label=self.voice.get(),
            )
        except (ConfigError, ValueError) as exc:
            messagebox.showerror("Suit-O", str(exc))

    def save(self) -> None:
        try:
            applied = self.app.apply_saved_voice(self.draft(), self.voice.get())
            self.app.save_preferences()
        except (ConfigError, ValueError, OSError) as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.show(applied)

    def reset(self) -> None:
        try:
            applied = self.app.reset_tuning()
            self.app.save_preferences()
        except (ConfigError, ValueError, OSError) as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.show(applied)

    def _selected_voice(self) -> str:
        label = self.voice.get().strip()
        if not label or label == ENGINE_DEFAULT_VOICE:
            return ""
        if is_clone_label(label):
            return profile_name_from_label(label)
        return label

    def _on_rate(self, value: str) -> None:
        self.rate_caption.configure(text=f"{int(round(float(value)))} wpm")

    def _on_pitch(self, value: str) -> None:
        self.pitch_caption.configure(text=str(int(round(float(value)))))

    def _on_pause(self, value: str) -> None:
        self.pause_caption.configure(text=f"{int(round(float(value)))} ms")

    def _slider(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        label: str,
        variable: tk.Variable,
        from_: int,
        to: int,
        command: Callable[[str], None],
        caption: ttk.Label,
    ) -> ttk.Scale:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(8, 0))
        scale = ttk.Scale(
            parent,
            from_=from_,
            to=to,
            orient="horizontal",
            variable=variable,
            command=command,
        )
        scale.grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        caption.grid(row=row, column=2, sticky="e", pady=(8, 0))
        return scale
