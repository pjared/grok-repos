"""Lineups tab: import images, order them, and set the overlay.

The tab edits files under ``lineups/``. It does not decide when a card is
shown during a match. That stays in ``suit_o.lineups``.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from suit_o.app import SuitOApp
from suit_o.config import ConfigError
from suit_o.lineups.library import (
    LibraryError,
    LineupCard,
    import_image,
    known_maps,
    list_cards,
    move_card,
    remove_card,
    rename_card,
    set_caption,
)
from suit_o.lineups.pack import PackError, import_pack as copy_lineup_pack, pack_cards
from suit_o.lineups.place import CORNERS

PREMIER_MAPS = (
    "de_ancient",
    "de_anubis",
    "de_dust2",
    "de_inferno",
    "de_mirage",
    "de_nuke",
    "de_overpass",
    "de_train",
    "de_vertigo",
)


class LineupsPanel:
    def __init__(self, parent: ttk.Frame, app: SuitOApp, *, on_saved) -> None:
        self.app = app
        self._on_saved = on_saved
        self._cards: list[LineupCard] = []
        self._photo: tk.PhotoImage | None = None

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        ttk.Label(
            parent,
            text=(
                "Put your own smoke screenshots in lineups/<map>/<t|ct>/, "
                "or import a lineup pack (a folder or zip with lineups.json). "
                "Pack photos stay in lineup-data/ on this machine. "
                "The overlay is a separate click-through window. It never reads game memory "
                "and its hotkeys are not sent to CS2. Use borderless or windowed mode."
            ),
            wraplength=700,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        picks = ttk.Frame(parent)
        picks.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        ttk.Label(picks, text="Map").grid(row=0, column=0, sticky="w")
        self.map_name = ttk.Combobox(picks, width=18, state="readonly")
        self.map_name.grid(row=0, column=1, sticky="w", padx=(6, 12))
        self.map_name.bind("<<ComboboxSelected>>", lambda _event: self.reload())
        ttk.Label(picks, text="Side").grid(row=0, column=2, sticky="w")
        self.side = ttk.Combobox(picks, width=6, state="readonly", values=("CT", "T"))
        self.side.grid(row=0, column=3, sticky="w", padx=(6, 0))
        self.side.set("CT")
        self.side.bind("<<ComboboxSelected>>", lambda _event: self.reload())

        body = ttk.Frame(parent)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self.cards = tk.Listbox(body, height=8, activestyle="dotbox")
        self.cards.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.cards.bind("<<ListboxSelect>>", lambda _event: self._show_selected())
        self.preview = tk.Label(body, bg="#f4f4f4", width=36, height=8, anchor="center")
        self.preview.grid(row=0, column=1, sticky="nsew")

        buttons = ttk.Frame(parent)
        buttons.grid(row=3, column=0, sticky="w", pady=(6, 4))
        ttk.Button(buttons, text="Import", command=self.import_files).grid(row=0, column=0)
        ttk.Button(buttons, text="Import pack", command=self.import_pack).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(buttons, text="Rename", command=self.rename).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(buttons, text="Caption", command=self.caption).grid(row=0, column=3, padx=(6, 0))
        ttk.Button(buttons, text="Up", command=lambda: self.move(-1)).grid(row=0, column=4, padx=(12, 0))
        ttk.Button(buttons, text="Down", command=lambda: self.move(1)).grid(row=0, column=5, padx=(6, 0))
        ttk.Button(buttons, text="Remove", command=self.remove).grid(row=0, column=6, padx=(6, 0))

        settings = self.app.config.lineups
        form = ttk.Frame(parent)
        form.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        form.columnconfigure(1, weight=1)
        self.enabled = tk.BooleanVar(value=settings.enabled)
        ttk.Checkbutton(form, text="Overlay enabled", variable=self.enabled).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.smokes_only = tk.BooleanVar(value=settings.smokes_only)
        ttk.Checkbutton(form, text="Smokes only", variable=self.smokes_only).grid(
            row=0, column=2, sticky="w"
        )
        ttk.Label(form, text="Width").grid(row=1, column=0, sticky="w")
        self.width = tk.DoubleVar(value=settings.width)
        ttk.Scale(form, from_=160, to=800, orient="horizontal", variable=self.width).grid(
            row=1, column=1, sticky="ew"
        )
        self.width_caption = ttk.Label(form, width=6)
        self.width_caption.grid(row=1, column=2, padx=(6, 0))
        self.width.trace_add("write", lambda *_args: self._paint_captions())
        ttk.Label(form, text="Opacity").grid(row=2, column=0, sticky="w")
        self.opacity = tk.DoubleVar(value=round(settings.opacity * 100))
        ttk.Scale(form, from_=30, to=100, orient="horizontal", variable=self.opacity).grid(
            row=2, column=1, sticky="ew"
        )
        self.opacity_caption = ttk.Label(form, width=6)
        self.opacity_caption.grid(row=2, column=2, padx=(6, 0))
        self.opacity.trace_add("write", lambda *_args: self._paint_captions())

        row = ttk.Frame(parent)
        row.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(row, text="Corner").grid(row=0, column=0, sticky="w")
        self.corner = ttk.Combobox(row, width=14, state="readonly", values=CORNERS)
        self.corner.set(settings.corner)
        self.corner.grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(row, text="Monitor").grid(row=0, column=2, sticky="w")
        self.monitor = ttk.Combobox(row, width=18, state="readonly")
        self.monitor.grid(row=0, column=3, sticky="w", padx=(6, 0))

        keys = ttk.Frame(parent)
        keys.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(keys, text="Next").grid(row=0, column=0, sticky="w")
        self.hotkey_next = tk.StringVar(value=settings.hotkey_next)
        ttk.Entry(keys, textvariable=self.hotkey_next, width=22).grid(row=0, column=1, padx=(6, 8))
        ttk.Label(keys, text="Previous").grid(row=0, column=2, sticky="w")
        self.hotkey_previous = tk.StringVar(value=settings.hotkey_previous)
        ttk.Entry(keys, textvariable=self.hotkey_previous, width=22).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(keys, text="Hide / show").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.hotkey_toggle = tk.StringVar(value=settings.hotkey_toggle)
        ttk.Entry(keys, textvariable=self.hotkey_toggle, width=22).grid(
            row=1, column=1, padx=(6, 8), pady=(4, 0)
        )
        ttk.Button(keys, text="Save overlay", command=self.save).grid(row=1, column=3, sticky="e", pady=(4, 0))

        self.status = ttk.Label(parent, wraplength=700, justify="left")
        self.status.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        self._paint_captions()
        self.reload_maps()

    def sync_from_app(self) -> None:
        """Paint the saved overlay settings after a content reload."""

        settings = self.app.config.lineups
        self.enabled.set(settings.enabled)
        self.smokes_only.set(settings.smokes_only)
        self.width.set(settings.width)
        self.opacity.set(round(settings.opacity * 100))
        if settings.corner in CORNERS:
            self.corner.set(settings.corner)
        self.hotkey_next.set(settings.hotkey_next)
        self.hotkey_previous.set(settings.hotkey_previous)
        self.hotkey_toggle.set(settings.hotkey_toggle)
        labels = list(self.monitor["values"])
        if labels and 0 <= settings.monitor < len(labels):
            self.monitor.set(labels[settings.monitor])
        self._paint_captions()

    def set_monitors(self, labels: list[str]) -> None:
        self.monitor["values"] = labels or ["Primary"]
        current = self.app.config.lineups.monitor
        if labels and 0 <= current < len(labels):
            self.monitor.set(labels[current])
        elif labels:
            self.monitor.set(labels[0])

    def reload_maps(self) -> None:
        found = known_maps(self.app.lineups_dir)
        names = list(PREMIER_MAPS)
        for name in found:
            if name not in names:
                names.append(name)
        self.map_name["values"] = names
        if self.map_name.get() not in names:
            self.map_name.set("de_dust2" if "de_dust2" in names else names[0])
        self.reload()

    def reload(self) -> None:
        side = self.side.get() or "CT"
        self._cards = list_cards(self.app.lineups_dir, self.map_name.get(), side)
        self._cards.extend(
            pack_cards(self.app.pack_dir, self.map_name.get(), side, smokes_only=False)
        )
        self.cards.delete(0, "end")
        for card in self._cards:
            label = card.caption if not card.lineup_id else f"{card.caption}  · pack"
            self.cards.insert("end", label)
        if self._cards:
            self.cards.selection_set(0)
            self._show_selected()
        else:
            self._photo = None
            self.preview.configure(image="", text="No images for this map and side yet.")
        self.status.configure(
            text=(
                f"{len(self._cards)} lineup(s) for {self.map_name.get()} {self.side.get()}. "
                "Shown while you hold a smoke, are alive, and the round is not over."
            )
        )

    def import_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.cards.winfo_toplevel(),
            title="Import lineup screenshots",
            filetypes=[("PNG images", "*.png")],
        )
        if not paths:
            return
        added = 0
        for raw in paths:
            try:
                import_image(
                    self.app.lineups_dir,
                    self.map_name.get(),
                    self.side.get(),
                    Path(raw),
                )
                added += 1
            except LibraryError as exc:
                messagebox.showerror("Suit-O", str(exc))
                break
        self.reload()
        self.status.configure(text=f"Imported {added} image(s).")

    def import_pack(self) -> None:
        """Copy a lineup pack folder or zip into the local lineup-data folder."""

        choice = messagebox.askyesnocancel(
            "Import pack",
            "Import a .zip lineup pack?\n\nYes opens a zip file.\nNo opens a folder.\nCancel stops.",
            parent=self.cards.winfo_toplevel(),
        )
        if choice is None:
            return
        parent = self.cards.winfo_toplevel()
        if choice:
            selected = filedialog.askopenfilename(
                parent=parent,
                title="Import lineup pack",
                filetypes=[("Zip pack", "*.zip")],
            )
        else:
            selected = filedialog.askdirectory(parent=parent, title="Import lineup pack folder")
        if not selected:
            return
        self.import_pack_from(Path(selected))

    def import_pack_from(self, path: Path) -> None:
        try:
            result = copy_lineup_pack(path, self.app.pack_dir)
        except PackError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload()
        self.status.configure(
            text=(
                f"Pack imported. {result.added} added, {result.replaced} replaced. "
                "Images stay in lineup-data/ on this machine."
            )
        )

    def rename(self) -> None:
        card = self._selected()
        if card is None:
            return
        if not self._folder_card(card):
            return
        name = simpledialog.askstring("Suit-O", "New lineup name", initialvalue=card.path.stem)
        if not name:
            return
        try:
            rename_card(card, name)
        except (LibraryError, OSError) as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload()

    def caption(self) -> None:
        card = self._selected()
        if card is None:
            return
        if not self._folder_card(card):
            return
        text = simpledialog.askstring("Suit-O", "Caption", initialvalue=card.caption)
        if text is None:
            return
        try:
            set_caption(card, text)
        except OSError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload()

    def move(self, delta: int) -> None:
        card = self._selected()
        if card is None:
            return
        if not self._folder_card(card):
            return
        try:
            move_card(self.app.lineups_dir, self.map_name.get(), self.side.get(), card.filename, delta)
        except LibraryError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload()

    def remove(self) -> None:
        card = self._selected()
        if card is None:
            return
        if not self._folder_card(card):
            return
        try:
            remove_card(card)
        except OSError as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        self.reload()

    def save(self) -> None:
        labels = list(self.monitor["values"])
        chosen = self.monitor.get()
        monitor = labels.index(chosen) if chosen in labels else 0
        try:
            self.app.save_lineup_preferences(
                enabled=bool(self.enabled.get()),
                width=int(round(float(self.width.get()))),
                opacity=float(self.opacity.get()) / 100.0,
                corner=self.corner.get() or "top-right",
                monitor=monitor,
                hotkey_next=self.hotkey_next.get(),
                hotkey_previous=self.hotkey_previous.get(),
                hotkey_toggle=self.hotkey_toggle.get(),
                smokes_only=bool(self.smokes_only.get()),
            )
        except (ConfigError, ValueError, OSError) as exc:
            messagebox.showerror("Suit-O", str(exc))
            return
        settings = self.app.config.lineups
        self.hotkey_next.set(settings.hotkey_next)
        self.hotkey_previous.set(settings.hotkey_previous)
        self.hotkey_toggle.set(settings.hotkey_toggle)
        self.status.configure(text="Overlay settings saved.")
        self._on_saved()

    def _folder_card(self, card: LineupCard) -> bool:
        if not card.lineup_id:
            return True
        messagebox.showerror(
            "Suit-O",
            "That lineup came from a pack. Import the pack again to replace it.",
        )
        return False

    def _selected(self) -> LineupCard | None:
        if not self.cards.curselection():
            return None
        index = int(self.cards.curselection()[0])
        if index < 0 or index >= len(self._cards):
            return None
        return self._cards[index]

    def _show_selected(self) -> None:
        card = self._selected()
        if card is None:
            return
        try:
            self._photo = _fit_photo(str(card.path), 280)
        except tk.TclError as exc:
            self.preview.configure(image="", text=str(exc))
            return
        self.preview.configure(image=self._photo, text="")

    def _paint_captions(self) -> None:
        try:
            self.width_caption.configure(text=str(int(round(float(self.width.get())))))
            self.opacity_caption.configure(text=f"{int(round(float(self.opacity.get())))}%")
        except (tk.TclError, ValueError):
            return


def _fit_photo(path: str, max_width: int) -> tk.PhotoImage:
    image = tk.PhotoImage(file=path)
    factor = 1
    while factor < 8 and image.width() // factor > max_width:
        factor += 1
    if factor == 1:
        return image
    return image.subsample(factor, factor)
