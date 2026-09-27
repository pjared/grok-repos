"""Clips page on Voice Training: cut one long take into a clip library.

The waveform is a Matplotlib figure. Silence splits go through auditok, and
saved clips are resampled with librosa. Playback uses the Listener tab's
output device and is never a microphone.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from suit_o.app import SuitOApp
from suit_o.gui.training import CONSENT
from suit_o.voice.clips import (
    ClipError,
    delete_regions,
    load_media,
    merge_regions,
    move_in,
    move_out,
    seek_time,
    split_on_silence,
    zoom_window,
)
from suit_o.voice.ffmpeg import FfmpegError
from suit_o.voice.library import ClipLibrary, ClipRecord, LibraryError
from suit_o.voice.script import ScriptError, load_script

_OPEN_TYPES = [
    ("Audio and video", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.mp4 *.mkv *.mov *.webm"),
    ("All files", "*.*"),
]
_NUDGE = 0.05
_SEEK = 0.1


class ClipsPanel:
    def __init__(self, parent: ttk.Frame, app: SuitOApp, *, schedule) -> None:
        self.app = app
        self._schedule = schedule
        self.samples: list[float] = []
        self.rate = 1
        self.position = 0.0
        self.in_point = 0.0
        self.out_point = 0.0
        self.view_start = 0.0
        self.view_span = 1.0
        self._regions: list[tuple[float, float]] = []
        self._peaks: list[tuple[float, float]] = []
        self._playing = False
        self._cancel = threading.Event()
        self._play_from = 0.0
        self._play_mark = 0.0
        self._tick_job: str | None = None
        self._drag_origin: tuple[float, float] | None = None
        self._source = ""

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(8, weight=1)
        ttk.Label(
            parent,
            text=(
                CONSENT
                + " Record one long take of the script, open it here, and chop it into clips."
            ),
            wraplength=820,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        source = ttk.Frame(parent)
        source.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        source.columnconfigure(2, weight=1)
        ttk.Label(source, text="Voice").grid(row=0, column=0, sticky="w")
        self.voice = tk.StringVar(value="Suit-O")
        entry = ttk.Entry(source, textvariable=self.voice, width=18)
        entry.grid(row=0, column=1, sticky="w", padx=(6, 12))
        entry.bind("<FocusOut>", lambda _event: self.reload_library())
        ttk.Button(source, text="Open recording", command=self.open_recording).grid(row=0, column=2, sticky="w")
        self.source_label = ttk.Label(source, text="No file open.")
        self.source_label.grid(row=0, column=3, sticky="w", padx=(8, 0))

        self._ax = None
        self._mpl = None
        self._env: tuple | None = None
        self.wave = self._build_waveform(parent)
        self.wave.grid(row=2, column=0, sticky="ew", pady=(4, 4))
        for key, handler in (
            ("<space>", self._toggle_play),
            ("<Left>", lambda _event: self._seek(-_SEEK)),
            ("<Right>", lambda _event: self._seek(_SEEK)),
            ("<i>", lambda _event: self.set_in()),
            ("<o>", lambda _event: self.set_out()),
            ("<I>", lambda _event: self.set_in()),
            ("<O>", lambda _event: self.set_out()),
            ("<comma>", lambda _event: self.nudge_in(-_NUDGE)),
            ("<period>", lambda _event: self.nudge_in(_NUDGE)),
            ("<Shift-Left>", lambda _event: self.nudge_in(-_NUDGE)),
            ("<Shift-Right>", lambda _event: self.nudge_in(_NUDGE)),
            ("<Control-Left>", lambda _event: self.nudge_out(-_NUDGE)),
            ("<Control-Right>", lambda _event: self.nudge_out(_NUDGE)),
            ("<bracketleft>", lambda _event: self.zoom(1.5)),
            ("<bracketright>", lambda _event: self.zoom(1 / 1.5)),
        ):
            self.wave.bind(key, handler)

        transport = ttk.Frame(parent)
        transport.grid(row=3, column=0, sticky="ew")
        ttk.Button(transport, text="Play", command=self.play).grid(row=0, column=0)
        ttk.Button(transport, text="Pause", command=self.pause).grid(row=0, column=1, padx=(6, 12))
        ttk.Button(transport, text="Set in", command=self.set_in).grid(row=0, column=2)
        ttk.Button(transport, text="Set out", command=self.set_out).grid(row=0, column=3, padx=(6, 12))
        ttk.Button(transport, text="In −", command=lambda: self.nudge_in(-_NUDGE)).grid(row=0, column=4)
        ttk.Button(transport, text="In +", command=lambda: self.nudge_in(_NUDGE)).grid(row=0, column=5, padx=(6, 8))
        ttk.Button(transport, text="Out −", command=lambda: self.nudge_out(-_NUDGE)).grid(row=0, column=6)
        ttk.Button(transport, text="Out +", command=lambda: self.nudge_out(_NUDGE)).grid(row=0, column=7, padx=(6, 12))
        ttk.Button(transport, text="Zoom out", command=lambda: self.zoom(1.5)).grid(row=0, column=8)
        ttk.Button(transport, text="Zoom in", command=lambda: self.zoom(1 / 1.5)).grid(row=0, column=9, padx=(6, 0))
        self.time_label = ttk.Label(transport, text="0.00 / 0.00")
        self.time_label.grid(row=0, column=10, sticky="w", padx=(12, 0))

        hint = ttk.Label(
            parent,
            text="Click the waveform, then: Space play/pause, drag in/out, I/O set points, arrows seek, ,/. nudge in, Ctrl+arrows nudge out, [ ] zoom.",
            wraplength=820,
        )
        hint.grid(row=4, column=0, sticky="w", pady=(4, 4))

        split = ttk.Frame(parent)
        split.grid(row=5, column=0, sticky="ew")
        ttk.Label(split, text="Energy").grid(row=0, column=0, sticky="w")
        self.threshold = tk.DoubleVar(value=55)
        ttk.Scale(split, from_=35, to=80, variable=self.threshold, length=120).grid(row=0, column=1, padx=(6, 8))
        ttk.Label(split, text="Min length").grid(row=0, column=2, sticky="w")
        self.min_length = tk.DoubleVar(value=0.4)
        ttk.Scale(split, from_=0.2, to=2.0, variable=self.min_length, length=120).grid(row=0, column=3, padx=(6, 8))
        ttk.Button(split, text="Auto-split on silence", command=self.auto_split).grid(row=0, column=4, padx=(8, 0))

        proposals = ttk.Frame(parent)
        proposals.grid(row=6, column=0, sticky="ew", pady=(6, 4))
        proposals.columnconfigure(0, weight=1)
        self.regions = tk.Listbox(proposals, height=4, selectmode="extended", exportselection=False)
        self.regions.grid(row=0, column=0, sticky="ew")
        actions = ttk.Frame(proposals)
        actions.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        ttk.Button(actions, text="Accept", command=self.accept_regions).grid(row=0, column=0, sticky="ew")
        ttk.Button(actions, text="Merge", command=self.merge_selected).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(actions, text="Delete", command=self.delete_selected).grid(row=2, column=0, sticky="ew", pady=(4, 0))

        save = ttk.Frame(parent)
        save.grid(row=7, column=0, sticky="ew", pady=(4, 4))
        save.columnconfigure(1, weight=1)
        ttk.Label(save, text="Label").grid(row=0, column=0, sticky="w")
        self.label = tk.StringVar()
        ttk.Entry(save, textvariable=self.label, width=24).grid(row=0, column=1, sticky="w", padx=(6, 8))
        ttk.Label(save, text="Script line").grid(row=0, column=2, sticky="w")
        self.script_line = ttk.Combobox(save, width=42, state="readonly")
        self.script_line.grid(row=0, column=3, sticky="ew", padx=(6, 0))
        self.script_line.bind("<<ComboboxSelected>>", lambda _event: self._apply_script_line())
        ttk.Label(save, text="Transcript").grid(row=1, column=0, sticky="nw", pady=(4, 0))
        self.transcript = tk.Text(save, height=2, wrap="word")
        self.transcript.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(save, text="Save selection", command=self.save_selection).grid(
            row=1, column=3, sticky="e", pady=(4, 0)
        )

        self.library = ttk.Treeview(
            parent,
            columns=("included", "duration", "transcript"),
            show="tree headings",
            height=6,
            selectmode="browse",
        )
        self.library.heading("#0", text="Label")
        self.library.heading("included", text="Training")
        self.library.heading("duration", text="Seconds")
        self.library.heading("transcript", text="Transcript")
        self.library.column("#0", width=160, stretch=True)
        self.library.column("included", width=80, stretch=False)
        self.library.column("duration", width=70, stretch=False)
        self.library.column("transcript", width=360, stretch=True)
        self.library.grid(row=8, column=0, sticky="nsew")

        library_buttons = ttk.Frame(parent)
        library_buttons.grid(row=9, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(library_buttons, text="Play clip", command=self.play_selected).grid(row=0, column=0)
        ttk.Button(library_buttons, text="Rename", command=self.rename_selected).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(library_buttons, text="Edit transcript", command=self.edit_transcript).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Button(library_buttons, text="Include / exclude", command=self.toggle_included).grid(
            row=0, column=3, padx=(6, 0)
        )
        ttk.Button(library_buttons, text="Delete clip", command=self.delete_clip).grid(row=0, column=4, padx=(6, 0))
        self.duration_label = ttk.Label(library_buttons, text="Included: 0.0s")
        self.duration_label.grid(row=0, column=5, sticky="w", padx=(12, 0))

        self.status = ttk.Label(parent, wraplength=820, justify="left")
        self.status.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        self._load_script_lines()
        self.reload_library()
        self._draw()

    def open_recording(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.wave.winfo_toplevel(),
            title="Open a long recording",
            filetypes=_OPEN_TYPES,
        )
        if not selected:
            return
        self.load_file(Path(selected))

    def load_file(self, path: Path) -> None:
        self.pause()
        try:
            samples, rate = load_media(path)
        except (FfmpegError, ClipError, OSError) as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        if not samples or rate < 1:
            messagebox.showerror("Suit-O", "That file has no audio.")
            return
        self.samples = samples
        self.rate = rate
        self.position = 0.0
        self.in_point = 0.0
        self.out_point = len(samples) / float(rate)
        self.view_start = 0.0
        self.view_span = self.out_point
        self._regions = []
        self._source = path.name
        self.source_label.configure(text=path.name)
        self._rebuild_peaks()
        self._paint_regions()
        self._draw()
        self.status.configure(
            text=(
                f"Loaded {path.name} ({self.out_point:.1f}s). "
                "Set in and out, or auto-split on silence."
            )
        )

    def play(self) -> None:
        if not self.samples:
            self.status.configure(text="Open a recording first.")
            return
        if self._playing:
            return
        self._playing = True
        self._cancel = threading.Event()
        self._play_from = self.position
        self._play_mark = time.monotonic()
        start = int(self.position * self.rate)
        chunk = self.samples[start:]
        output = self.app.config.speech.output_device
        cancel = self._cancel

        def run() -> None:
            error = ""
            try:
                from suit_o.voice.capture import play_samples

                play_samples(chunk, self.rate, output, cancel=cancel)
            except Exception as exc:
                error = str(exc)
            self._schedule(lambda: self._play_finished(error))

        threading.Thread(target=run, name="suit-o-clip-play", daemon=True).start()
        self._tick()

    def pause(self) -> None:
        self._playing = False
        self._cancel.set()
        if self._tick_job is not None:
            try:
                self.wave.after_cancel(self._tick_job)
            except tk.TclError:
                pass
            self._tick_job = None
        self._draw()

    def set_in(self) -> None:
        self.in_point = move_in(self.position, self.out_point, 0.0)
        self._draw()

    def set_out(self) -> None:
        self.out_point = move_out(self.in_point, self.position, 0.0, self._duration())
        self._draw()

    def nudge_in(self, delta: float) -> None:
        self.in_point = move_in(self.in_point, self.out_point, delta)
        self._draw()

    def nudge_out(self, delta: float) -> None:
        self.out_point = move_out(self.in_point, self.out_point, delta, self._duration())
        self._draw()

    def zoom(self, factor: float) -> None:
        self.view_start, self.view_span = zoom_window(
            self.view_start,
            self.view_span,
            self._duration(),
            self.position,
            factor,
        )
        self._draw()

    def auto_split(self) -> None:
        if not self.samples:
            self.status.configure(text="Open a recording first.")
            return
        try:
            self._regions = split_on_silence(
                self.samples,
                self.rate,
                threshold=float(self.threshold.get()),
                min_length=float(self.min_length.get()),
            )
        except ClipError as exc:
            self.status.configure(text=str(exc))
            return
        self._paint_regions()
        self.status.configure(text=f"Proposed {len(self._regions)} clip(s). Accept, merge, or delete them.")

    def merge_selected(self) -> None:
        indexes = list(self.regions.curselection())
        self._regions = merge_regions(self._regions, indexes)
        self._paint_regions()

    def delete_selected(self) -> None:
        indexes = list(self.regions.curselection())
        self._regions = delete_regions(self._regions, indexes)
        self._paint_regions()

    def accept_regions(self) -> None:
        indexes = list(self.regions.curselection())
        chosen = [self._regions[index] for index in indexes] if indexes else list(self._regions)
        if not chosen:
            self.status.configure(text="Auto-split first, or save the in/out selection.")
            return
        transcript = self._transcript() if len(chosen) == 1 else ""
        saved = 0
        library = self._library()
        for number, (start, end) in enumerate(chosen, start=1):
            label = self.label.get().strip() if len(chosen) == 1 else f"Clip {number}"
            try:
                library.add_clip(
                    self.samples,
                    self.rate,
                    start,
                    end,
                    label=label or f"Clip {number}",
                    transcript=transcript,
                    included=True,
                )
            except (ClipError, LibraryError, OSError) as exc:
                messagebox.showerror("Suit-O", str(exc))
                break
            saved += 1
        if saved == len(chosen):
            if indexes:
                self._regions = delete_regions(self._regions, indexes)
            else:
                self._regions = []
        self._paint_regions()
        self.reload_library()
        self.status.configure(text=f"Saved {saved} clip(s) into the {self.voice.get().strip() or 'Suit-O'} library.")

    def save_selection(self) -> None:
        if not self.samples:
            self.status.configure(text="Open a recording first.")
            return
        try:
            record = self._library().add_clip(
                self.samples,
                self.rate,
                self.in_point,
                self.out_point,
                label=self.label.get().strip() or "Clip",
                transcript=self._transcript(),
                included=True,
            )
        except (ClipError, LibraryError, OSError) as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload_library()
        self.status.configure(text=f"Saved {record.label or record.id} ({record.duration_seconds:.1f}s).")

    def reload_library(self) -> None:
        try:
            clips = self._library().clips()
            included = self._library().included_duration()
        except LibraryError as exc:
            self.status.configure(text=str(exc))
            clips = []
            included = 0.0
        children = self.library.get_children()
        if children:
            self.library.delete(*children)
        for clip in clips:
            self.library.insert(
                "",
                "end",
                iid=clip.id,
                text=clip.label or clip.id,
                values=("included" if clip.included else "excluded", f"{clip.duration_seconds:.1f}", clip.transcript),
            )
        self.duration_label.configure(text=f"Included: {included:.1f}s")

    def play_selected(self) -> None:
        clip = self._selected()
        if clip is None:
            return
        path = self._library().directory / clip.filename
        self.load_file(path)

    def rename_selected(self) -> None:
        clip = self._selected()
        if clip is None:
            return
        name = simpledialog.askstring("Suit-O", "Clip label", initialvalue=clip.label)
        if name is None:
            return
        try:
            self._library().update(clip.id, label=name)
        except LibraryError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload_library()

    def edit_transcript(self) -> None:
        clip = self._selected()
        if clip is None:
            return
        text = simpledialog.askstring("Suit-O", "Transcript", initialvalue=clip.transcript)
        if text is None:
            return
        try:
            self._library().update(clip.id, transcript=text)
        except LibraryError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload_library()

    def toggle_included(self) -> None:
        clip = self._selected()
        if clip is None:
            return
        try:
            self._library().update(clip.id, included=not clip.included)
        except LibraryError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload_library()

    def delete_clip(self) -> None:
        clip = self._selected()
        if clip is None:
            return
        try:
            self._library().delete(clip.id)
        except (LibraryError, OSError) as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload_library()

    def _library(self) -> ClipLibrary:
        return ClipLibrary(self.app.voices_dir, self.voice.get().strip() or "Suit-O")

    def _selected(self) -> ClipRecord | None:
        chosen = self.library.selection()
        if not chosen:
            return None
        clip_id = str(chosen[0])
        for clip in self._library().clips():
            if clip.id == clip_id:
                return clip
        return None

    def _transcript(self) -> str:
        return self.transcript.get("1.0", "end").strip()

    def _apply_script_line(self) -> None:
        line = self.script_line.get().strip()
        if not line or line == "(none)":
            return
        self.transcript.delete("1.0", "end")
        self.transcript.insert("1.0", line)
        if not self.label.get().strip():
            self.label.set(line[:48])

    def _load_script_lines(self) -> None:
        try:
            lines = load_script()
        except ScriptError:
            lines = []
        self.script_line["values"] = ("(none)", *lines)
        self.script_line.set("(none)")

    def _duration(self) -> float:
        if not self.samples or self.rate < 1:
            return 0.0
        return len(self.samples) / float(self.rate)

    def _build_waveform(self, parent: ttk.Frame) -> tk.Widget:
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            return ttk.Label(
                parent,
                text=(
                    "The waveform needs Matplotlib. From the suit-o-cs2 folder run: "
                    "python -m pip install -r requirements-voice.txt"
                ),
                wraplength=820,
            )
        figure = Figure(figsize=(8, 1.35), dpi=80, facecolor="#1b1b1b")
        self._ax = figure.add_axes((0, 0, 1, 1))
        canvas = FigureCanvasTkAgg(figure, master=parent)
        self._mpl = canvas
        widget = canvas.get_tk_widget()
        widget.configure(height=130, background="#1b1b1b", highlightthickness=0)
        canvas.mpl_connect("button_press_event", self._press)
        canvas.mpl_connect("motion_notify_event", self._drag)
        canvas.mpl_connect("button_release_event", self._release)
        return widget

    def _rebuild_peaks(self) -> None:
        samples = self.samples
        if not samples or self.rate < 1:
            self._env = None
            return
        try:
            import numpy as np
        except ImportError:
            self._env = None
            return
        audio = np.asarray(samples, dtype=np.float32)
        buckets = 2400
        size = max(1, int(len(audio) // buckets))
        usable = (len(audio) // size) * size
        if usable < size:
            self._env = None
            return
        shaped = audio[:usable].reshape(-1, size)
        times = (np.arange(shaped.shape[0]) * size + size / 2) / float(self.rate)
        self._env = (times, shaped.min(axis=1), shaped.max(axis=1))

    def _paint_regions(self) -> None:
        self.regions.delete(0, "end")
        for start, end in self._regions:
            self.regions.insert("end", f"{start:.2f}–{end:.2f}  ({end - start:.2f}s)")

    def _toggle_play(self, _event: object) -> str:
        if self._playing:
            self.pause()
        else:
            self.play()
        return "break"

    def _seek(self, delta: float) -> str:
        was = self._playing
        self.pause()
        self.position = seek_time(self.position, delta, self._duration())
        self._draw()
        if was:
            self.play()
        return "break"

    def _event_time(self, event: object) -> float | None:
        xdata = getattr(event, "xdata", None)
        if xdata is not None:
            return float(xdata)
        x = getattr(event, "x", None)
        if x is None:
            return None
        return self._time_at(int(x))

    def _press(self, event: object) -> None:
        self.wave.focus_set()
        when = self._event_time(event)
        if when is None:
            return
        self._drag_origin = (float(getattr(event, "x", 0) or 0), when)

    def _drag(self, event: object) -> None:
        if self._drag_origin is None:
            return
        when = self._event_time(event)
        if when is None:
            return
        if abs(float(getattr(event, "x", 0) or 0) - self._drag_origin[0]) < 4:
            return
        start = self._drag_origin[1]
        self.in_point = min(start, when)
        self.out_point = max(start, when)
        if self.out_point - self.in_point < 0.05:
            self.out_point = min(self._duration(), self.in_point + 0.05)
        self._draw()

    def _release(self, event: object) -> None:
        origin = self._drag_origin
        self._drag_origin = None
        if origin is None:
            return
        when = self._event_time(event)
        if when is None:
            return
        if abs(float(getattr(event, "x", 0) or 0) - origin[0]) < 4:
            was = self._playing
            self.pause()
            self.position = when
            self._draw()
            if was:
                self.play()

    def _time_at(self, x: int) -> float:
        width = max(1, self.wave.winfo_width())
        fraction = min(1.0, max(0.0, float(x) / float(width)))
        return self.view_start + fraction * self.view_span

    def _tick(self) -> None:
        if not self._playing:
            return
        self.position = self._play_from + (time.monotonic() - self._play_mark)
        if self.position >= self._duration():
            self.position = self._duration()
            self.pause()
            return
        self._draw()
        self._tick_job = self.wave.after(50, self._tick)

    def _play_finished(self, error: str) -> None:
        self._playing = False
        if error:
            self.status.configure(text=error)
        self._draw()

    def _draw(self) -> None:
        duration = self._duration()
        if self.view_span <= 0:
            self.view_span = duration or 1.0
        self.time_label.configure(
            text=f"{self.position:.2f} / {duration:.2f}   in {self.in_point:.2f}  out {self.out_point:.2f}"
        )
        axis = self._ax
        canvas = self._mpl
        if axis is None or canvas is None:
            return
        axis.clear()
        axis.set_facecolor("#1b1b1b")
        axis.set_xlim(self.view_start, self.view_start + self.view_span)
        axis.set_ylim(-1.05, 1.05)
        axis.axis("off")
        if self.out_point > self.in_point:
            axis.axvspan(self.in_point, self.out_point, color="#16351f", zorder=0)
        if self._env is not None and duration > 0:
            times, lows, highs = self._env
            axis.fill_between(times, lows, highs, color="#7eb6ff", linewidth=0, zorder=1)
        axis.axvline(self.in_point, color="#7dcea0", linewidth=1, zorder=2)
        axis.axvline(self.out_point, color="#f5b041", linewidth=1, zorder=2)
        axis.axvline(self.position, color="#f2f2f2", linewidth=1, zorder=3)
        try:
            canvas.draw_idle()
        except tk.TclError:
            return
