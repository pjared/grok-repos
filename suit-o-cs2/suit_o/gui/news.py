"""What's new. The text comes from CHANGELOG.md. Nothing here cuts a version."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from suit_o.changelog import ReleaseNotes, format_whats_new


class WhatsNew:
    """A small window of changelog sections."""

    def __init__(self, master: tk.Misc, title: str, notes: list[ReleaseNotes]) -> None:
        self.window = tk.Toplevel(master)
        self.window.title(title)
        self.window.geometry("720x480")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        frame = ttk.Frame(self.window, padding=(12, 12, 12, 12))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.body = tk.Text(frame, wrap="word", height=18, state="disabled")
        self.body.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=self.body.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.body.configure(yscrollcommand=scroll.set)
        self.body.configure(state="normal")
        self.body.insert("1.0", format_whats_new(notes))
        self.body.configure(state="disabled")
        ttk.Button(frame, text="Close", command=self.window.destroy).grid(row=1, column=0, sticky="e", pady=(8, 0))
