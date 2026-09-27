"""Voice Training tab: record a script, then store a cloned-voice profile.

Recording uses a microphone. Playback uses the Listener tab's output device,
which still cannot be a microphone or a virtual cable.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from suit_o.app import SuitOApp
from suit_o.config import ConfigError
from suit_o.gui.drops import enable_file_drop
from suit_o.voice.clips import ClipError
from suit_o.voice.intake import IntakeError, classify_path, import_short_clip
from suit_o.voice.library import ClipLibrary, LibraryError
from suit_o.voice.runtime import runtime_status
from suit_o.voice.script import DEFAULT_SCRIPT_PATH, ScriptError, load_script
from suit_o.voice.session import MIN_BUILD_SECONDS, RecordingSession, SessionError

_FILE_TYPES = [
    ("Recordings", "*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.mkv *.mov *.webm *.avi"),
    ("All files", "*.*"),
]

CONSENT = (
    "Record your own voice, or someone who agreed to be recorded. "
    "Do not use ripped game audio or an actor's voice."
)


class _LiveRecorder:
    """Background microphone capture. The level is polled from the UI thread."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._level = [0.0]
        self._thread: threading.Thread | None = None
        self._wav = b""
        self._error: Exception | None = None

    def start(self, device_name: str) -> None:
        self._cancel.clear()
        self._wav = b""
        self._error = None
        self._level[0] = 0.0

        def run() -> None:
            try:
                from suit_o.voice.capture import record_wav

                self._wav = record_wav(device_name, self._cancel, self._level)
            except Exception as exc:
                self._error = exc

        self._thread = threading.Thread(target=run, name="suit-o-record", daemon=True)
        self._thread.start()

    def stop(self) -> bytes:
        self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._error is not None:
            raise self._error
        return self._wav

    def level(self) -> float:
        return float(self._level[0])


class TrainingPanel:
    def __init__(self, parent: ttk.Frame, app: SuitOApp, *, on_profile_built, schedule, on_long_file=None) -> None:
        self.app = app
        self._on_profile_built = on_profile_built
        self._schedule = schedule
        self._on_long_file = on_long_file
        self._recorder = _LiveRecorder()
        self._playing = False
        self._meter_job: str | None = None
        self.session = self._new_session()
        self.runtime = runtime_status()

        parent.columnconfigure(0, weight=1)
        consent = ttk.Label(parent, text=CONSENT, wraplength=680, justify="left")
        consent.grid(row=0, column=0, sticky="ew")
        self.runtime_label = ttk.Label(parent, wraplength=680, justify="left")
        self.runtime_label.grid(row=1, column=0, sticky="ew", pady=(6, 8))

        mic_row = ttk.Frame(parent)
        mic_row.grid(row=2, column=0, sticky="ew")
        mic_row.columnconfigure(1, weight=1)
        ttk.Label(mic_row, text="Microphone").grid(row=0, column=0, sticky="w")
        self.microphone = ttk.Combobox(mic_row, state="readonly", width=48)
        self.microphone.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(mic_row, text="Refresh", command=self.reload_microphones).grid(row=0, column=2)

        self.progress = ttk.Label(parent)
        self.progress.grid(row=3, column=0, sticky="w", pady=(8, 4))
        self.line_label = ttk.Label(parent)
        self.line_label.grid(row=4, column=0, sticky="w")
        self.line_text = tk.Text(
            parent,
            height=4,
            wrap="word",
            relief="solid",
            borderwidth=1,
            bg="#ffffff",
            fg="#1a1a1a",
        )
        self.line_text.grid(row=5, column=0, sticky="ew", pady=(4, 8))

        buttons = ttk.Frame(parent)
        buttons.grid(row=6, column=0, sticky="w")
        self.record_button = ttk.Button(buttons, text="Record", command=self.record)
        self.record_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop)
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.play_button = ttk.Button(buttons, text="Play back", command=self.play)
        self.play_button.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.rerecord_button = ttk.Button(buttons, text="Re-record", command=self.rerecord)
        self.rerecord_button.grid(row=0, column=3, sticky="w", padx=(8, 0))
        ttk.Button(buttons, text="Previous", command=self.previous).grid(
            row=0, column=4, sticky="w", padx=(16, 0)
        )
        ttk.Button(buttons, text="Next", command=self.next).grid(row=0, column=5, sticky="w", padx=(8, 0))

        meter_row = ttk.Frame(parent)
        meter_row.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(meter_row, text="Level").grid(row=0, column=0, sticky="w")
        self.meter = ttk.Progressbar(meter_row, maximum=100, length=280)
        self.meter.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(
            parent,
            text="Playback uses the output device on the Listener tab. The microphone is only for these samples.",
            wraplength=680,
        ).grid(row=8, column=0, sticky="w", pady=(4, 8))

        build_row = ttk.Frame(parent)
        build_row.grid(row=9, column=0, sticky="ew")
        build_row.columnconfigure(1, weight=1)
        ttk.Label(build_row, text="Voice name").grid(row=0, column=0, sticky="w")
        self.name = tk.StringVar(value="Suit-O")
        ttk.Entry(build_row, textvariable=self.name, width=24).grid(
            row=0, column=1, sticky="w", padx=(8, 8)
        )
        self.build_button = ttk.Button(build_row, text="Build voice", command=self.build)
        self.build_button.grid(row=0, column=2, sticky="w")
        ttk.Button(build_row, text="Reload script", command=self.reload_script).grid(
            row=0, column=3, sticky="w", padx=(8, 0)
        )

        self.status = ttk.Label(parent, wraplength=680, justify="left")
        self.status.grid(row=10, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            parent,
            text=f"Script file: {DEFAULT_SCRIPT_PATH.name}. About a minute of audio is required (aim for 1–3 minutes).",
            wraplength=680,
        ).grid(row=11, column=0, sticky="w", pady=(4, 0))

        files = ttk.Frame(parent)
        files.grid(row=12, column=0, sticky="ew", pady=(8, 0))
        files.columnconfigure(2, weight=1)
        ttk.Button(files, text="Add files...", command=self.add_files).grid(row=0, column=0, sticky="w")
        self.library_label = ttk.Label(files, text="Usable: 0s")
        self.library_label.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.name.trace_add("write", lambda *_args: self._paint_duration())
        ttk.Label(
            parent,
            text=(
                "Drop wav, mp3, m4a, flac, ogg, or a video here. "
                "Under 30 seconds becomes a library clip with a transcript you can edit. "
                "Longer files open in Clips so you can cut them. Build voice uses the included clips."
            ),
            wraplength=680,
            justify="left",
        ).grid(row=13, column=0, sticky="ew", pady=(4, 0))
        enable_file_drop(parent, self.import_paths)

        self.reload_microphones()
        self._paint()

    def reload_microphones(self) -> None:
        self.runtime = runtime_status()
        self.runtime_label.configure(text=self.runtime.summary)
        if not self.runtime.installed:
            self.microphone["values"] = ()
            self.microphone.set("")
            return
        try:
            from suit_o.voice.capture import list_input_device_names

            names = list_input_device_names()
        except Exception as exc:
            self.status.configure(text=str(exc))
            names = []
        self.microphone["values"] = names
        if names and self.microphone.get() not in names:
            self.microphone.set(names[0])

    def record(self) -> None:
        if not self._require_runtime():
            return
        device = self.microphone.get().strip()
        try:
            self.session.set_microphone(device)
            self.session.start_recording()
            self._recorder.start(device)
        except (SessionError, ConfigError, OSError, RuntimeError) as exc:
            self.session.cancel_recording()
            messagebox.showerror("Suit-O", str(exc))
            return
        self._paint()
        self._poll_meter()

    def stop(self) -> None:
        if self.session.state == "playing":
            self._playing = False
            self.session.finish_playback()
            self._paint()
            return
        if self.session.state != "recording":
            return
        try:
            wav = self._recorder.stop()
            self.session.stop_recording(wav)
        except (SessionError, OSError, RuntimeError) as exc:
            self.session.cancel_recording()
            messagebox.showerror("Suit-O", str(exc))
        self.meter["value"] = 0
        self._paint()

    def play(self) -> None:
        if not self._require_runtime():
            return
        try:
            path = self.session.start_playback()
        except SessionError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self._playing = True
        self._paint()
        output = self.app.config.speech.output_device

        def run() -> None:
            error = ""
            try:
                from suit_o.voice.capture import play_wav_file

                play_wav_file(path, output)
            except Exception as exc:
                error = str(exc)
            self._schedule(lambda: self._playback_finished(error))

        threading.Thread(target=run, name="suit-o-playback", daemon=True).start()

    def rerecord(self) -> None:
        try:
            self.session.rerecord()
        except SessionError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self._paint()

    def previous(self) -> None:
        self._move(self.session.previous_line)

    def next(self) -> None:
        self._move(self.session.next_line)

    def reload_script(self) -> None:
        if self.session.recorded_count:
            messagebox.showerror(
                "Suit-O",
                "Reload is available before you record. Finish or discard this pass first.",
            )
            return
        if self.session.state != "idle":
            messagebox.showerror("Suit-O", "Stop recording or playback before reloading the script")
            return
        try:
            self.session = self._new_session()
        except ScriptError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self._paint()

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self.line_text.winfo_toplevel(),
            title="Add recordings",
            filetypes=_FILE_TYPES,
        )
        if not selected:
            return
        self.import_paths([Path(item) for item in selected])

    def import_paths(
        self,
        paths: list[Path],
        *,
        transcripts: dict[Path, str] | None = None,
        ask_transcript: bool | None = None,
    ) -> None:
        """Add short recordings to the named voice. Long ones go to Clips."""

        if ask_transcript is None:
            ask_transcript = transcripts is None
        name = self.name.get().strip() or "Suit-O"
        library = ClipLibrary(self.app.voices_dir, name)
        added = 0
        longs: list[Path] = []
        problems: list[str] = []
        for raw in paths:
            item = classify_path(Path(raw))
            if item.kind == "rejected":
                problems.append(item.detail)
                continue
            if item.kind == "long":
                longs.append(item.path)
                continue
            supplied = _supplied_transcript(item.path, transcripts)
            if supplied is not None:
                transcript = supplied
            elif ask_transcript:
                typed = simpledialog.askstring(
                    "Suit-O",
                    f"Transcript for {item.path.name}",
                    parent=self.line_text.winfo_toplevel(),
                )
                transcript = "" if typed is None else typed
            else:
                transcript = ""
            try:
                import_short_clip(item.path, library, transcript=transcript)
            except (IntakeError, ClipError, LibraryError, OSError) as exc:
                problems.append(str(exc))
                continue
            added += 1
        if longs and self._on_long_file is not None:
            self._on_long_file(longs[0])
        usable = self.session.recorded_seconds + library.included_duration()
        bits: list[str] = []
        if added:
            bits.append(f"Added {added} clip(s) to {name}. Edit the transcript on the Clips page.")
        if longs:
            rest = ""
            if len(longs) > 1:
                rest = " Also long: " + ", ".join(path.name for path in longs[1:]) + "."
            where = "Opened" if self._on_long_file is not None else "Cut"
            bits.append(f"{where} {longs[0].name} in Clips (30s or longer).{rest}")
        if problems:
            bits.append(" ".join(problems))
        bits.append(f"Usable audio: {usable:.0f}s.")
        self._paint()
        self.status.configure(text=" ".join(bits))

    def build(self) -> None:
        if self.session.state != "idle":
            messagebox.showerror("Suit-O", "Stop recording or playback before building")
            return
        name = self.name.get().strip() or "Suit-O"
        from suit_o.voice.library import included_wavs

        extras = included_wavs(self.app.voices_dir, name)
        try:
            profile = self.session.build(name, self.app.voices_dir, extra_wavs=extras)
        except SessionError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.runtime = runtime_status()
        extra = ""
        if not self.runtime.installed:
            extra = " " + self.runtime.summary
        clip_note = f"Used {len(extras)} library clip(s). " if extras else ""
        self.status.configure(
            text=(
                f"Saved {profile.name} ({profile.duration_seconds:.0f}s). "
                f"It is in the Voice tab as {profile.label}. "
                f"{clip_note}"
                "Every stock line is rendered to audio for this voice. "
                "Matches play those files only. Preview is the only live synthesis."
                + extra
            )
        )
        self._on_profile_built(profile.name)
        self._paint()

    def _move(self, step) -> None:
        try:
            step()
        except SessionError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self._paint()

    def _new_session(self) -> RecordingSession:
        folder = self.app.voices_dir / "_session"
        return RecordingSession(load_script(), folder)

    def _require_runtime(self) -> bool:
        self.runtime = runtime_status()
        self.runtime_label.configure(text=self.runtime.summary)
        if self.runtime.installed:
            return True
        messagebox.showinfo("Suit-O", self.runtime.summary)
        return False

    def _poll_meter(self) -> None:
        if self.session.state != "recording":
            self.meter["value"] = 0
            return
        rms = self._recorder.level()
        self.meter["value"] = max(0, min(100, int(round(min(1.0, rms * 4) * 100))))
        root = self.line_text.winfo_toplevel()
        self._meter_job = root.after(80, self._poll_meter)

    def _playback_finished(self, error: str) -> None:
        self._playing = False
        self.session.finish_playback()
        if error:
            messagebox.showerror("Suit-O", error)
        self._paint()

    def _paint(self) -> None:
        session = self.session
        self._paint_duration()
        self.line_label.configure(text=f"Line {session.index + 1} of {session.total}")
        self.line_text.configure(state="normal")
        self.line_text.delete("1.0", "end")
        self.line_text.insert("1.0", session.line_text())
        self.line_text.configure(state="disabled")
        if session.state == "recording":
            self.status.configure(text="Recording. Press Stop when the line is finished.")
        elif session.has_take():
            self.status.configure(text="This line has a take. Play it back, or re-record it.")
        else:
            self.status.configure(text="Record this line in your own voice, or add a recording you already have.")

    def _paint_duration(self) -> None:
        session = self.session
        library_seconds = _library_seconds(self.app.voices_dir, self.name.get())
        usable = session.recorded_seconds + library_seconds
        self.progress.configure(
            text=(
                f"{session.recorded_count} of {session.total} recorded"
                f" · {usable:.0f}s usable"
                f" (need about {MIN_BUILD_SECONDS:.0f}s)"
            )
        )
        self.library_label.configure(
            text=f"Usable: {usable:.0f}s (script {session.recorded_seconds:.0f}s + library {library_seconds:.0f}s)"
        )


def _supplied_transcript(path: Path, transcripts: dict | None) -> str | None:
    if transcripts is None:
        return None
    if path in transcripts:
        return str(transcripts[path])
    if path.name in transcripts:
        return str(transcripts[path.name])
    return ""


def _library_seconds(voices_dir: Path, voice_name: str) -> float:
    try:
        return ClipLibrary(voices_dir, voice_name.strip() or "Suit-O").included_duration()
    except (LibraryError, OSError):
        return 0.0
