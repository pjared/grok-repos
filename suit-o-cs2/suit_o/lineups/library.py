"""Load and edit user-supplied lineup images.

Layout: ``lineups/<map>/<t|ct>/<name>.png``. A sidecar ``<name>.txt`` is the
caption. ``order.txt`` is the display order. No images are shipped with Suit-O.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_IMAGE_SUFFIXES = {".png"}
_ORDER_FILE = "order.txt"
_MAP_PREFIXES = ("de_", "cs_", "ar_")
_SLUG = re.compile(r"[^a-z0-9._-]+")


class LibraryError(ValueError):
    """A lineup file could not be imported or renamed."""


@dataclass(frozen=True)
class LineupCard:
    """One image the overlay can show."""

    path: Path
    caption: str

    @property
    def filename(self) -> str:
        return self.path.name


def map_folder_names(token: str) -> list[str]:
    """Folder names to try for a CS2 map id, most specific first.

    ``de_dust2`` matches ``lineups/de_dust2`` and then ``lineups/dust2``.
    """

    raw = token.strip().lower().replace(" ", "").replace("-", "_")
    if not raw:
        return []
    names = [raw]
    for prefix in _MAP_PREFIXES:
        if raw.startswith(prefix) and raw[len(prefix) :]:
            short = raw[len(prefix) :]
            if short not in names:
                names.append(short)
    if not any(raw.startswith(prefix) for prefix in _MAP_PREFIXES):
        long = "de_" + raw
        if long not in names:
            names.append(long)
    return names


def side_folder(side: str) -> str:
    """``T`` or ``CT`` to the folder name ``t`` or ``ct``."""

    token = side.strip().lower()
    if token in {"t", "terrorist"}:
        return "t"
    if token in {"ct", "counter-terrorist", "counterterrorist"}:
        return "ct"
    raise LibraryError("Side must be T or CT")


def resolve_side_dir(root: Path, map_token: str, side: str, *, create: bool = False) -> Path:
    """Directory that holds one side's images. Prefers an existing map folder."""

    side_name = side_folder(side)
    names = map_folder_names(map_token)
    if not names:
        raise LibraryError("Map name is empty")
    for name in names:
        folder = root / name / side_name
        if folder.is_dir() or (root / name).is_dir():
            if create:
                folder.mkdir(parents=True, exist_ok=True)
            return folder
    folder = root / names[0] / side_name
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_cards(root: Path, map_token: str, side: str) -> list[LineupCard]:
    """Images for one map and side, in ``order.txt`` order, then by filename."""

    try:
        folder = resolve_side_dir(root, map_token, side)
    except LibraryError:
        return []
    if not folder.is_dir():
        return []
    images = {
        path.name: path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
    }
    ordered: list[Path] = []
    seen: set[str] = set()
    order_path = folder / _ORDER_FILE
    if order_path.is_file():
        for line in order_path.read_text(encoding="utf-8").splitlines():
            name = line.strip()
            if name in images and name not in seen:
                ordered.append(images[name])
                seen.add(name)
    rest = sorted((name for name in images if name not in seen), key=str.lower)
    ordered.extend(images[name] for name in rest)
    return [LineupCard(path=path, caption=_caption(path)) for path in ordered]


def import_image(root: Path, map_token: str, side: str, source: Path) -> LineupCard:
    """Copy a PNG into the lineup folder. The filename becomes the first caption."""

    if source.suffix.lower() not in _IMAGE_SUFFIXES:
        raise LibraryError("Lineup images must be PNG files")
    if not source.is_file():
        raise LibraryError(f"Image not found: {source}")
    folder = resolve_side_dir(root, map_token, side, create=True)
    dest = folder / _unique_name(folder, _slug_filename(source.stem))
    shutil.copyfile(source, dest)
    _write_order(folder, [card.filename for card in list_cards(root, map_token, side)])
    return LineupCard(path=dest, caption=_caption(dest))


def rename_card(card: LineupCard, new_name: str) -> LineupCard:
    """Rename the image and its caption file. ``new_name`` is a display name, not a path."""

    folder = card.path.parent
    filename = _unique_name(folder, _slug_filename(new_name), keep=card.path.name)
    dest = folder / filename
    if dest != card.path:
        card.path.rename(dest)
        sidecar = _sidecar(card.path)
        if sidecar.is_file():
            sidecar.rename(_sidecar(dest))
    _rewrite_order_name(folder, card.filename, dest.name)
    return LineupCard(path=dest, caption=_caption(dest))


def set_caption(card: LineupCard, caption: str) -> LineupCard:
    """Store a caption beside the image. Blank deletes the sidecar."""

    text = caption.strip()
    sidecar = _sidecar(card.path)
    if not text:
        if sidecar.is_file():
            sidecar.unlink()
        return LineupCard(path=card.path, caption=_caption(card.path))
    sidecar.write_text(text + "\n", encoding="utf-8")
    return LineupCard(path=card.path, caption=text)


def move_card(root: Path, map_token: str, side: str, filename: str, delta: int) -> list[LineupCard]:
    """Move one card earlier (negative) or later (positive) and save ``order.txt``."""

    cards = list_cards(root, map_token, side)
    names = [card.filename for card in cards]
    if filename not in names:
        raise LibraryError(f"No lineup named {filename!r}")
    index = names.index(filename)
    target = index + delta
    if target < 0 or target >= len(names):
        return cards
    names[index], names[target] = names[target], names[index]
    folder = cards[0].path.parent
    _write_order(folder, names)
    return list_cards(root, map_token, side)


def remove_card(card: LineupCard) -> None:
    """Delete an image the user imported, plus its caption."""

    if card.path.is_file():
        card.path.unlink()
    sidecar = _sidecar(card.path)
    if sidecar.is_file():
        sidecar.unlink()
    _rewrite_order_name(card.path.parent, card.filename, "")


def known_maps(root: Path) -> list[str]:
    """Map folder names that already exist, plus an empty list when the root is missing."""

    if not root.is_dir():
        return []
    names = [path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")]
    return sorted(names, key=str.lower)


def _caption(path: Path) -> str:
    sidecar = _sidecar(path)
    if sidecar.is_file():
        text = sidecar.read_text(encoding="utf-8").strip()
        if text:
            return text
    return path.stem.replace("_", " ").replace("-", " ")


def _sidecar(path: Path) -> Path:
    return path.with_suffix(".txt")


def _slug_filename(name: str) -> str:
    stem = name.strip().lower().replace(" ", "_")
    stem = _SLUG.sub("", stem).strip("._")
    if not stem:
        raise LibraryError("Lineup name is empty")
    if not stem.endswith(".png"):
        stem += ".png"
    return stem


def _unique_name(folder: Path, filename: str, *, keep: str = "") -> str:
    if filename == keep or not (folder / filename).exists():
        return filename
    stem = Path(filename).stem
    for number in range(2, 100):
        candidate = f"{stem}-{number}.png"
        if candidate == keep or not (folder / candidate).exists():
            return candidate
    raise LibraryError(f"Too many lineups named {stem}")


def _write_order(folder: Path, names: list[str]) -> None:
    payload = "\n".join(names)
    if payload:
        payload += "\n"
    (folder / _ORDER_FILE).write_text(payload, encoding="utf-8")


def _rewrite_order_name(folder: Path, old: str, new: str) -> None:
    order_path = folder / _ORDER_FILE
    if not order_path.is_file():
        if new:
            _write_order(folder, [new])
        return
    names = []
    for line in order_path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name == old:
            if name == old and new:
                names.append(new)
            continue
        names.append(name)
    if new and new not in names:
        names.append(new)
    _write_order(folder, names)
