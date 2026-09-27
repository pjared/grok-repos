"""Chat tab. Suit-O talks only outside a live match.

The transcript lives in the text widget and in ``ChatSession``. It is not
written to the event log or to a file.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from collections.abc import Iterator
from tkinter import ttk

from suit_o.app import SuitOApp
from suit_o.chat.idle import IdleRelease
from suit_o.chat.llm import ChatError, load_chat_settings, release_model, stream_reply
from suit_o.chat.session import PAUSED, ChatSession
from suit_o.chat.stt import WHISPER_INSTALL, SttError, transcribe, whisper_available

_HINT = (
    "Type to Suit-O. He answers in text and in the voice selected on the Voice tab "
    "(a cloned voice, when that is the one selected), through the output device on the Listener tab. "
    "A live round pauses chat. The menu, warmup, and the time between matches stay open."
)
VRAM_NOTE = "Live chat with CS2 open needs roughly 7 to 9 GB of VRAM."


class ChatPanel:
    def __init__(
        self,
        parent: ttk.Frame,
        app: SuitOApp,
        *,
        schedule,
        threaded: bool = True,
        generate=None,
        on_release=None,
    ) -> None:
        self.app = app
        self._schedule = schedule
        self._threaded = threaded
        self._generate_override = generate
        self._on_release = on_release
        self.session = ChatSession()
        self._idle = IdleRelease(self._release_resident)
        self._busy = False
        self._generation = 0
        self._worker: threading.Thread | None = None

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=_HINT, wraplength=820, justify="left").grid(row=0, column=0, sticky="ew")
        self.vram_note = ttk.Label(header, text=VRAM_NOTE, wraplength=820, justify="left")
        self.vram_note.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.history = tk.Text(parent, height=16, wrap="word", state="disabled")
        self.history.grid(row=1, column=0, sticky="nsew", pady=(8, 8))

        compose = ttk.Frame(parent)
        compose.grid(row=2, column=0, sticky="ew")
        compose.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(compose)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda _event: self.send())
        self.send_button = ttk.Button(compose, text="Send", command=self.send)
        self.send_button.grid(row=0, column=1, padx=(8, 0))
        self.stop_button = ttk.Button(compose, text="Stop", command=self.stop)
        self.stop_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Button(compose, text="Clear chat", command=self.clear).grid(row=0, column=3, padx=(8, 0))

        talk = ttk.Frame(parent)
        talk.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        talk.columnconfigure(1, weight=1)
        self.talk_button = ttk.Button(talk, text="Hold to talk")
        self.talk_button.grid(row=0, column=0, sticky="w")
        self.talk_button.bind("<ButtonPress-1>", self._talk_down)
        self.talk_button.bind("<ButtonRelease-1>", self._talk_up)
        self.talk_hint = ttk.Label(talk, wraplength=640, justify="left")
        self.talk_hint.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._talk_cancel = threading.Event()
        self._talking = False

        self.status = ttk.Label(parent, wraplength=820, justify="left")
        self.status.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self._paint_talk()
        self.sync_paused(False)

    def sync_paused(self, paused: bool) -> None:
        if paused:
            self.status.configure(text=PAUSED)
            self.send_button.state(["disabled"])
            self.entry.state(["disabled"])
            return
        if not self._busy:
            self.send_button.state(["!disabled"])
            self.entry.state(["!disabled"])
            if self.status.cget("text") == PAUSED:
                self.status.configure(text="")

    def send(self) -> None:
        text = self.entry.get().strip()
        if not text or self._busy:
            return
        if self.app.match_is_live():
            self.sync_paused(True)
            return
        self.entry.delete(0, "end")
        self._idle.touch(time.monotonic())
        self._append(f"You: {text}\n\nSuit-O: ")
        self._busy = True
        generation = self._generation
        self.send_button.state(["disabled"])
        self.status.configure(text="")

        def work() -> None:
            try:
                for kind, piece in self.session.reply(
                    text,
                    paused=self.app.match_is_live,
                    generate=self._generate,
                    speak=self._speak,
                ):
                    if generation != self._generation:
                        break
                    if kind == "token":
                        self._schedule(lambda chunk=piece, gen=generation: self._append_live(gen, chunk))
                    elif kind == "status":
                        self._schedule(
                            lambda message=piece, gen=generation: self._set_status(gen, message)
                        )
            except ChatError as exc:
                self._schedule(lambda message=str(exc), gen=generation: self._set_status(gen, message))
            finally:
                self._schedule(lambda gen=generation: self._finish(gen))

        if self._threaded:
            self._worker = threading.Thread(target=work, name="suit-o-chat", daemon=True)
            self._worker.start()
        else:
            work()

    def stop(self) -> None:
        self.session.stop()
        self._talk_cancel.set()
        try:
            self.app.interrupt_chat()
        except Exception:
            pass
        self.status.configure(text="Stopped.")

    def clear(self) -> None:
        busy = self._busy
        self._generation += 1
        self.session.clear()
        self._talk_cancel.set()
        if busy:
            try:
                self.app.interrupt_chat()
            except Exception:
                pass
        self._busy = False
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")
        if self.app.match_is_live():
            self.sync_paused(True)
            return
        self.send_button.state(["!disabled"])
        self.entry.state(["!disabled"])
        self.status.configure(text="Cleared.")

    def poll_idle(self, now: float | None = None) -> bool:
        """Release a resident model after a quiet spell, or as soon as a round is live."""

        moment = time.monotonic() if now is None else now
        return self._idle.poll(
            moment,
            busy=self._busy or self._talking,
            paused=self.app.match_is_live(),
        )

    def _release_resident(self) -> None:
        if self._on_release is not None:
            self._on_release()
            return
        try:
            release_model(load_chat_settings(getattr(self.app, "config_path", None)))
        except Exception:
            return

    def fill_from_speech(self, samples: list[float], sample_rate: int) -> None:
        """Put a transcript in the box. Tests pass samples and a fake transcriber."""

        if self.app.match_is_live():
            self.sync_paused(True)
            return
        try:
            text = transcribe(samples, sample_rate, transcriber=getattr(self, "_transcriber", None))
        except SttError as exc:
            self.status.configure(text=str(exc))
            return
        if text:
            self.entry.configure(state="normal")
            self.entry.delete(0, "end")
            self.entry.insert(0, text)

    def _generate(self, messages: list[dict]) -> Iterator[str]:
        if self._generate_override is not None:
            return self._generate_override(messages)
        settings = load_chat_settings(getattr(self.app, "config_path", None))
        return stream_reply(settings, messages)

    def _speak(self, sentence: str) -> None:
        if self.app.match_is_live():
            return
        self.app.speak_chat(sentence)

    def _finish(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._generation:
            return
        self._busy = False
        self._append("\n\n")
        if not self.app.match_is_live():
            self.send_button.state(["!disabled"])
            self.entry.state(["!disabled"])

    def _append_live(self, generation: int, text: str) -> None:
        if generation != self._generation:
            return
        self._append(text)

    def _set_status(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self.status.configure(text=message)

    def _append(self, text: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", text)
        self.history.see("end")
        self.history.configure(state="disabled")

    def _paint_talk(self) -> None:
        if whisper_available():
            self.talk_button.state(["!disabled"])
            self.talk_hint.configure(text="Hold the button and talk. Letting go types what you said.")
            return
        self.talk_button.state(["disabled"])
        self.talk_hint.configure(text=WHISPER_INSTALL)

    def _talk_down(self, _event: object) -> None:
        if not whisper_available() or self.app.match_is_live():
            if self.app.match_is_live():
                self.sync_paused(True)
            return
        self._talk_cancel.clear()
        self._talking = True
        self.status.configure(text="Listening...")

        def run() -> None:
            samples: list[float] = []
            error = ""
            try:
                samples = _record_until(self._talk_cancel)
            except Exception as exc:
                error = str(exc)
            self._schedule(lambda: self._talk_done(samples, error))

        threading.Thread(target=run, name="suit-o-chat-mic", daemon=True).start()

    def _talk_up(self, _event: object) -> None:
        self._talk_cancel.set()

    def _talk_done(self, samples: list[float], error: str) -> None:
        self._talking = False
        if error:
            self.status.configure(text=error)
            return
        if not samples:
            self.status.configure(text="")
            return
        self.fill_from_speech(samples, 16000)

    def set_transcriber(self, transcriber) -> None:
        """Tests inject this so push-to-talk never loads a model."""

        self._transcriber = transcriber


def _record_until(cancel: threading.Event) -> list[float]:
    """Record mono float samples until ``cancel`` is set. Not used by tests."""

    try:
        import sounddevice as sd
    except ImportError as exc:
        raise SttError(WHISPER_INSTALL) from exc
    import numpy as np

    chunks: list = []

    def callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
        chunks.append(indata.copy())

    try:
        stream = sd.InputStream(samplerate=16000, channels=1, dtype="float32", callback=callback)
    except Exception as exc:
        raise SttError(f"Could not open the microphone. {exc}") from exc
    with stream:
        while not cancel.is_set():
            cancel.wait(0.05)
    if not chunks:
        return []
    joined = np.concatenate(chunks, axis=0).reshape(-1)
    return [float(sample) for sample in joined]
