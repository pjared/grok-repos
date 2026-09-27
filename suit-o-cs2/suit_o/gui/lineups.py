"""Lineups tab: browse a pack, import images, and set the overlay.

The tab edits files under ``lineups/`` and reads ``lineup-data/``. It does not
decide when a card is shown during a match. That stays in ``suit_o.lineups``.
Copy setpos puts practice-server text on the clipboard. It is never sent to CS2.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from suit_o.app import SuitOApp
from suit_o.config import ConfigError
from suit_o.gui.grenade_icons import grenade_icons
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
from suit_o.lineups.pack import (
    PACK_FILENAME,
    PackError,
    import_pack as copy_lineup_pack,
    load_pack_file,
    map_counts,
    note_extra_fields,
    pack_cards,
)
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
_SIDES = ("All", "T", "CT")
_GRENADES = ("All", "smoke", "flash", "molotov", "he")
_STATUSES = ("All", "draft", "verified")


class LineupsPanel:
    def __init__(self, parent: ttk.Frame, app: SuitOApp, *, on_saved) -> None:
        self.app = app
        self._on_saved = on_saved
        self._cards: list[LineupCard] = []
        self._map_keys: list[str | None] = []
        self._filling_maps = False
        self._photo: tk.PhotoImage | None = None
        self._aim_photo: tk.PhotoImage | None = None
        self._source_url = ""
        self._seen_extra_fields: set[str] = set()
        self._icons = grenade_icons(parent)

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        ttk.Label(
            parent,
            text=(
                "Every lineup in an imported pack is listed here. Filter by map, side, "
                "grenade, and status. Folder screenshots in lineups/<map>/<t|ct>/ are smokes. "
                "Pack photos stay in lineup-data/ on this machine and are not committed. "
                "The overlay follows the grenade in your hand. Copy setpos copies practice-server "
                "text only. That string is never sent to CS2."
            ),
            wraplength=820,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        picks = ttk.Frame(parent)
        picks.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        ttk.Label(picks, text="Side").grid(row=0, column=0, sticky="w")
        self.side = ttk.Combobox(picks, width=6, state="readonly", values=_SIDES)
        self.side.grid(row=0, column=1, sticky="w", padx=(6, 12))
        self.side.set("All")
        self.side.bind("<<ComboboxSelected>>", lambda _event: self.reload())
        ttk.Label(picks, text="Grenade").grid(row=0, column=2, sticky="w")
        self.grenade = ttk.Combobox(picks, width=10, state="readonly", values=_GRENADES)
        self.grenade.grid(row=0, column=3, sticky="w", padx=(6, 12))
        self.grenade.set("All")
        self.grenade.bind("<<ComboboxSelected>>", lambda _event: self.reload())
        ttk.Label(picks, text="Status").grid(row=0, column=4, sticky="w")
        self.status_filter = ttk.Combobox(picks, width=10, state="readonly", values=_STATUSES)
        self.status_filter.grid(row=0, column=5, sticky="w", padx=(6, 0))
        self.status_filter.set("All")
        self.status_filter.bind("<<ComboboxSelected>>", lambda _event: self.reload())

        body = ttk.Frame(parent)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)
        self.maps = tk.Listbox(body, height=8, width=18, activestyle="dotbox", exportselection=False)
        self.maps.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        self.maps.bind("<<ListboxSelect>>", self._on_map)
        self.cards = ttk.Treeview(
            body,
            columns=("map", "side", "status"),
            show="tree headings",
            height=8,
            selectmode="browse",
        )
        self.cards.heading("#0", text="Lineup")
        self.cards.heading("map", text="Map")
        self.cards.heading("side", text="Side")
        self.cards.heading("status", text="Status")
        self.cards.column("#0", width=200, stretch=True)
        self.cards.column("map", width=72, stretch=False)
        self.cards.column("side", width=44, stretch=False)
        self.cards.column("status", width=68, stretch=False)
        self.cards.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        self.cards.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

        preview = ttk.Frame(body)
        preview.grid(row=0, column=2, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.columnconfigure(1, weight=1)
        photos = ttk.Frame(preview)
        photos.grid(row=0, column=0, columnspan=2, sticky="nsew")
        photos.columnconfigure(0, weight=1)
        photos.columnconfigure(1, weight=1)
        self.preview = tk.Label(photos, bg="#f4f4f4", width=18, height=6, anchor="center")
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview_aim = tk.Label(photos, bg="#f4f4f4", width=18, height=6, anchor="center")
        self.preview_aim.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(preview, text="setpos").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.copy_button = ttk.Button(preview, text="Copy setpos", command=self.copy_setpos)
        self.copy_button.grid(row=1, column=1, sticky="e", pady=(6, 0))
        self.setpos_box = tk.Text(preview, height=3, wrap="word", width=28)
        self.setpos_box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.setpos_box.configure(state="disabled")
        ttk.Label(
            preview,
            text="Practice server only. Never sent to CS2.",
            wraplength=260,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.notes_label = ttk.Label(preview, text="", wraplength=280, justify="left")
        self.notes_label.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.source_link = tk.Label(
            preview,
            text="",
            fg="#0b57d0",
            cursor="hand2",
            wraplength=280,
            justify="left",
            anchor="w",
        )
        self.source_link.grid(row=5, column=0, columnspan=2, sticky="ew")
        self.source_link.bind("<Button-1>", self._open_source)

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

        self.status = ttk.Label(parent, wraplength=820, justify="left")
        self.status.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        self._paint_captions()
        self.copy_button.state(["disabled"])
        self.reload_maps()

    def sync_from_app(self) -> None:
        """Paint the saved overlay settings after a content reload."""

        settings = self.app.config.lineups
        self.enabled.set(settings.enabled)
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
        previous = self._current_map_key()
        labels = ["All maps"]
        keys: list[str | None] = [None]
        seen: set[str] = set()
        pack = self._loaded_pack()
        for name, count in map_counts(pack) if pack is not None else []:
            key = name.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            labels.append(f"{name} ({count})")
            keys.append(name)
        folder_names = list(PREMIER_MAPS)
        for name in known_maps(self.app.lineups_dir):
            if name not in folder_names:
                folder_names.append(name)
        for name in folder_names:
            short = name[3:] if name.startswith(("de_", "cs_", "ar_")) else name
            if name.lower() in seen or short.lower() in seen:
                continue
            labels.append(name)
            keys.append(name)
            seen.add(name.lower())
        self._filling_maps = True
        try:
            self.maps.delete(0, "end")
            for label in labels:
                self.maps.insert("end", label)
            self._map_keys = keys
            chosen = 0
            for index, key in enumerate(keys):
                if key == previous or (
                    isinstance(key, str) and isinstance(previous, str) and key.lower() == previous.lower()
                ):
                    chosen = index
                    break
            self.maps.selection_clear(0, "end")
            self.maps.selection_set(chosen)
            self.maps.activate(chosen)
        finally:
            self._filling_maps = False
        self.reload()

    def reload(self) -> None:
        self._cards = self._folder_cards()
        self._cards.extend(
            pack_cards(
                self.app.pack_dir,
                self._current_map_key(),
                self._filter_value(self.side.get()),
                grenade=self._filter_value(self.grenade.get()),
                status=self._filter_value(self.status_filter.get()),
            )
        )
        children = self.cards.get_children()
        if children:
            self.cards.delete(*children)
        for index, card in enumerate(self._cards):
            icon = self._icons.get(card.grenade)
            kwargs = {}
            if icon is not None:
                kwargs["image"] = icon
            self.cards.insert(
                "",
                "end",
                iid=str(index),
                text=card.name or card.caption,
                values=(self._card_map(card), self._card_side(card), card.status),
                **kwargs,
            )
        if self._cards:
            self.cards.selection_set("0")
            self.cards.focus("0")
            self._show_selected()
        else:
            self._clear_preview("No lineups for this filter.")
        map_label = self.maps.get(self.maps.curselection()[0]) if self.maps.curselection() else "All maps"
        self.status.configure(
            text=(
                f"{len(self._cards)} lineup(s) for {map_label}. "
                "The overlay follows the grenade in your hand while you are alive "
                "and the round is not over."
            )
        )

    def import_files(self) -> None:
        target = self._import_target()
        if target is None:
            return
        map_name, side = target
        paths = filedialog.askopenfilenames(
            parent=self.maps.winfo_toplevel(),
            title="Import lineup screenshots",
            filetypes=[("PNG images", "*.png")],
        )
        if not paths:
            return
        added = 0
        for raw in paths:
            try:
                import_image(self.app.lineups_dir, map_name, side, Path(raw))
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
            parent=self.maps.winfo_toplevel(),
        )
        if choice is None:
            return
        parent = self.maps.winfo_toplevel()
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
        self._note_pack_extras(result.unknown_fields)
        self.reload_maps()
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
        map_name, side = self._folder_place(card)
        try:
            move_card(self.app.lineups_dir, map_name, side, card.filename, delta)
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

    def copy_setpos(self) -> None:
        """Copy practice-server console text. Nothing is sent to CS2."""

        card = self._selected()
        if card is None or not card.setpos:
            return
        top = self.maps.winfo_toplevel()
        top.clipboard_clear()
        top.clipboard_append(card.setpos)
        self.status.configure(text="Copied")

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
                smokes_only=self.app.config.lineups.smokes_only,
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

    def _on_map(self, _event: object) -> None:
        if self._filling_maps:
            return
        self.reload()

    def _loaded_pack(self):
        path = self.app.pack_dir / PACK_FILENAME
        if not path.is_file():
            return None
        try:
            pack = load_pack_file(path)
        except PackError:
            return None
        self._note_pack_extras(pack.unknown_fields)
        return pack

    def _current_map_key(self) -> str | None:
        if not self._map_keys:
            return None
        selected = self.maps.curselection()
        if not selected:
            return None
        index = int(selected[0])
        if index < 0 or index >= len(self._map_keys):
            return None
        return self._map_keys[index]

    def _filter_value(self, value: str) -> str | None:
        token = (value or "").strip()
        if not token or token.lower() == "all":
            return None
        return token

    def _folder_cards(self) -> list[LineupCard]:
        if self._filter_value(self.grenade.get()) not in {None, "smoke"}:
            return []
        if self._filter_value(self.status_filter.get()) is not None:
            return []
        side = self._filter_value(self.side.get())
        sides = ("T", "CT") if side is None else (side,)
        map_key = self._current_map_key()
        maps = [key for key in self._map_keys if key] if map_key is None else [map_key]
        cards: list[LineupCard] = []
        seen: set[Path] = set()
        for name in maps:
            for one_side in sides:
                for card in list_cards(self.app.lineups_dir, name, one_side):
                    if card.path in seen:
                        continue
                    seen.add(card.path)
                    cards.append(card)
        return cards

    def _import_target(self) -> tuple[str, str] | None:
        map_key = self._current_map_key()
        side = self.side.get()
        if not map_key:
            messagebox.showerror("Suit-O", "Pick a map before importing screenshots.")
            return None
        if side not in {"T", "CT"}:
            messagebox.showerror("Suit-O", "Pick T or CT before importing screenshots.")
            return None
        return map_key, side

    def _folder_card(self, card: LineupCard) -> bool:
        if not card.lineup_id:
            return True
        messagebox.showerror(
            "Suit-O",
            "That lineup came from a pack. Import the pack again to replace it.",
        )
        return False

    def _folder_place(self, card: LineupCard) -> tuple[str, str]:
        return card.path.parent.parent.name, card.path.parent.name

    def _selected(self) -> LineupCard | None:
        selected = self.cards.selection()
        if not selected:
            return None
        try:
            index = int(selected[0])
        except ValueError:
            return None
        if index < 0 or index >= len(self._cards):
            return None
        return self._cards[index]

    def _card_map(self, card: LineupCard) -> str:
        if card.map_name:
            return card.map_name
        return card.path.parent.parent.name

    def _card_side(self, card: LineupCard) -> str:
        if card.side:
            return card.side
        return card.path.parent.name.upper()

    def _show_selected(self) -> None:
        card = self._selected()
        if card is None:
            return
        try:
            self._photo = _fit_photo(str(card.path), 180)
        except tk.TclError as exc:
            self._clear_preview(str(exc))
            self._set_setpos(card.setpos)
            self._set_notes(card.notes, card.source_url)
            return
        self.preview.configure(image=self._photo, text="")
        if card.aim_path is not None:
            try:
                self._aim_photo = _fit_photo(str(card.aim_path), 180)
            except tk.TclError:
                self._aim_photo = None
                self.preview_aim.configure(image="", text="")
            else:
                self.preview_aim.configure(image=self._aim_photo, text="")
        else:
            self._aim_photo = None
            self.preview_aim.configure(image="", text="")
        self._set_setpos(card.setpos)
        self._set_notes(card.notes, card.source_url)
        if card.setpos:
            self.copy_button.state(["!disabled"])
        else:
            self.copy_button.state(["disabled"])

    def _clear_preview(self, message: str) -> None:
        self._photo = None
        self._aim_photo = None
        self.preview.configure(image="", text=message)
        self.preview_aim.configure(image="", text="")
        self._set_setpos("")
        self._set_notes("", "")
        self.copy_button.state(["disabled"])

    def _set_setpos(self, text: str) -> None:
        self.setpos_box.configure(state="normal")
        self.setpos_box.delete("1.0", "end")
        if text:
            self.setpos_box.insert("1.0", text)
        self.setpos_box.configure(state="disabled")

    def _set_notes(self, notes: str, source_url: str) -> None:
        self.notes_label.configure(text=notes)
        url = source_url.strip()
        self._source_url = url if url.startswith(("http://", "https://")) else ""
        if url:
            self.source_link.configure(text=url)
        else:
            self.source_link.configure(text="")

    def _open_source(self, _event: object = None) -> None:
        if self._source_url:
            webbrowser.open(self._source_url)

    def _note_pack_extras(self, names: tuple[str, ...]) -> None:
        note_extra_fields(names, self.app.note, seen=self._seen_extra_fields)

    def _paint_captions(self) -> None:
        try:
            self.width_caption.configure(text=str(int(round(float(self.width.get())))))
            self.opacity_caption.configure(text=f"{int(round(float(self.opacity.get())))}%")
        except (tk.TclError, ValueError):
            return


def _fit_photo(path: str, max_width: int) -> tk.PhotoImage:
    from suit_o.gui.photos import fit_photo

    return fit_photo(path, max_width)
