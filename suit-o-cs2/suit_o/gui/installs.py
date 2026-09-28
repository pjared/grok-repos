"""Installations window. One checkbox per optional part of Suit-O.

Nothing is installed until the user ticks a part and clicks Install selected.
Commands run with their console hidden, and progress shows in this window.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from suit_o.installs.components import (
    BY_KEY,
    COMPONENTS,
    InstallError,
    Probes,
    plan,
    python_label,
    python_supports_voice,
    run_plan,
)

INSTALLED = "Installed"
NOT_INSTALLED = "Not installed"
NEEDS_311 = "Needs Python 3.11"


class InstallsWindow:
    def __init__(
        self,
        master: tk.Misc,
        *,
        schedule: Callable[[Callable[[], None]], None],
        probes: Probes | None = None,
        on_installed: Callable[[list[str]], None] = lambda _files: None,
        on_move_python: Callable[[], None] | None = None,
        python_version: tuple[int, int] | None = None,
        threaded: bool = True,
        runner=None,
        pull=None,
        planner=plan,
    ) -> None:
        self._schedule = schedule
        self.probes = probes or Probes()
        self._on_installed = on_installed
        self._on_move_python = on_move_python
        self._python_version = python_version
        self._threaded = threaded
        self._runner = runner
        self._pull = pull
        self._planner = planner
        self._busy = False
        self._stop = False
        self.supported = python_supports_voice(python_version)

        self.window = tk.Toplevel(master)
        self.window.title("Installations")
        self.window.geometry("760x560")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        frame = ttk.Frame(self.window, padding=(14, 12, 14, 12))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(
            frame,
            text="Tick what you want, then click Install selected. Everything installs on this PC.",
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        self.python_row = ttk.Frame(frame)
        self.python_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.python_row.columnconfigure(0, weight=1)
        self.python_note = ttk.Label(self.python_row, wraplength=560, justify="left", foreground="#9a5b00")
        self.python_note.grid(row=0, column=0, sticky="w")
        self.move_button = ttk.Button(self.python_row, text="Move to Python 3.11", command=self._move_python)
        self.move_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        if self.supported:
            self.python_row.grid_remove()
        else:
            self.python_note.configure(
                text=(
                    f"Suit-O is running on Python {python_label(python_version)}. Voice training and "
                    "recording clean-up need Python 3.11. Moving closes Suit-O, sets it up on 3.11, "
                    "and opens it again. Your settings and voices are kept."
                )
            )

        rows = ttk.Frame(frame)
        rows.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        rows.columnconfigure(1, weight=1)
        self.checks: dict[str, tk.BooleanVar] = {}
        self.boxes: dict[str, ttk.Checkbutton] = {}
        self.states: dict[str, ttk.Label] = {}
        for row, component in enumerate(COMPONENTS):
            var = tk.BooleanVar(value=False)
            box = ttk.Checkbutton(
                rows,
                text=component.label,
                variable=var,
                command=lambda key=component.key: self._toggled(key),
            )
            box.grid(row=row * 2, column=0, sticky="w", pady=(6, 0))
            state = ttk.Label(rows, text="")
            state.grid(row=row * 2, column=2, sticky="e", pady=(6, 0))
            ttk.Label(
                rows,
                text=f"{component.description} ({component.size})",
                foreground="#555555",
            ).grid(row=row * 2 + 1, column=0, columnspan=3, sticky="w", padx=(24, 0))
            self.checks[component.key] = var
            self.boxes[component.key] = box
            self.states[component.key] = state

        self.log = tk.Text(frame, height=10, wrap="word", state="disabled")
        self.log.grid(row=3, column=0, sticky="nsew", pady=(12, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        actions.columnconfigure(0, weight=1)
        self.status = ttk.Label(actions, text="")
        self.status.grid(row=0, column=0, sticky="w")
        self.install_button = ttk.Button(actions, text="Install selected", command=self.install)
        self.install_button.grid(row=0, column=1, padx=(8, 0))
        self.stop_button = ttk.Button(actions, text="Stop", command=self.stop)
        self.stop_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Button(actions, text="Close", command=self.close).grid(row=0, column=3, padx=(8, 0))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def refresh(self) -> None:
        """Re-check what is installed and paint each row."""

        for component in COMPONENTS:
            key = component.key
            installed = self.probes.installed(key)
            blocked = component.needs_supported_python and not self.supported
            if installed:
                text, state = INSTALLED, ["disabled"]
                self.checks[key].set(False)
            elif blocked:
                text, state = NEEDS_311, ["disabled"]
                self.checks[key].set(False)
            else:
                text, state = NOT_INSTALLED, ["!disabled"]
            self.states[key].configure(text=text)
            self.boxes[key].state(state)
        self._paint_buttons()

    def selected(self) -> list[str]:
        return [key for key, var in self.checks.items() if var.get()]

    def _toggled(self, key: str) -> None:
        """Ticking a part also ticks what it needs. Unticking a need unticks its users."""

        if self.checks[key].get():
            for need in BY_KEY[key].needs:
                if "disabled" not in self.boxes[need].state():
                    self.checks[need].set(True)
        else:
            for other in COMPONENTS:
                if key in other.needs:
                    self.checks[other.key].set(False)
        self._paint_buttons()

    def _paint_buttons(self) -> None:
        if self._busy:
            self.install_button.state(["disabled"])
            self.stop_button.state(["!disabled"])
            return
        self.stop_button.state(["disabled"])
        self.install_button.state(["!disabled"] if self.selected() else ["disabled"])

    def install(self) -> None:
        chosen = self.selected()
        if self._busy or not chosen:
            return
        try:
            steps = self._planner(
                chosen,
                installed=self.probes.installed,
                python_version=self._python_version,
            )
        except InstallError as exc:
            self.status.configure(text=str(exc))
            return
        if not steps:
            self.status.configure(text="Already installed.")
            self.refresh()
            return
        self._busy = True
        self._stop = False
        for box in self.boxes.values():
            box.state(["disabled"])
        self._paint_buttons()
        self.status.configure(text="Installing. This can take a while; Suit-O keeps working.")

        def work() -> None:
            files: list[str] = []
            error = ""
            try:
                files = run_plan(
                    steps,
                    runner=self._runner,
                    progress=lambda message: self._schedule(lambda text=message: self._append(text)),
                    pull=self._pull,
                    cancelled=lambda: self._stop,
                )
            except InstallError as exc:
                error = str(exc)
            except Exception as exc:
                error = f"Install failed. {exc}"
            self._schedule(lambda: self._finished(files, error))

        if self._threaded:
            threading.Thread(target=work, name="suit-o-install", daemon=True).start()
        else:
            work()

    def stop(self) -> None:
        """Stop after the step that is running now."""

        if self._busy:
            self._stop = True
            self.status.configure(text="Stopping after this step...")

    def _finished(self, files: list[str], error: str) -> None:
        self._busy = False
        try:
            self.refresh()
        except tk.TclError:
            return
        if error:
            self.status.configure(text=error)
            self._append(error)
            return
        self.status.configure(text="Installed. Suit-O will reload so the new parts turn on.")
        self._on_installed(files)

    def _move_python(self) -> None:
        if self._busy or self._on_move_python is None:
            return
        self._on_move_python()

    def _append(self, text: str) -> None:
        try:
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        except tk.TclError:
            return

    def close(self) -> None:
        if self._busy:
            self.status.configure(text="Still installing. Click Stop first, or leave this open.")
            return
        try:
            self.window.destroy()
        except tk.TclError:
            return
