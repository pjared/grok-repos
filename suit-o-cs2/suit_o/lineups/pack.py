"""Lineup packs: a versioned lineups.json plus stand and aim photos.

The schema is ``lineups/pack.schema.json``. Imported images stay in
``lineup-data/``, which git ignores. They are for the player's own use.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from suit_o.lineups.library import LineupCard, map_folder_names

PACK_VERSION = 1
PACK_FILENAME = "lineups.json"
GRENADES = frozenset({"smoke", "flash", "molotov", "he"})
SIDES = frozenset({"T", "CT"})
STATUSES = frozenset({"draft", "verified"})
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_REQUIRED = (
    "id",
    "map",
    "side",
    "grenade",
    "name",
    "stand",
    "aim",
    "throw_type",
    "throw",
    "covers",
    "stand_image",
    "aim_image",
    "setpos",
    "status",
)
_OPTIONAL_STRINGS = (
    "notes",
    "source_url",
    "source_timestamp",
    "second_source_url",
)
_OPTIONAL_BOOL = "verified_by_second_source"
_KNOWN_LINEUP = set(_REQUIRED) | set(_OPTIONAL_STRINGS) | {_OPTIONAL_BOOL}
_KNOWN_PACK = frozenset({"version", "maps", "lineups"})


class PackError(ValueError):
    """A lineup pack is missing, outdated, or unsafe to copy."""


@dataclass(frozen=True)
class PackLineup:
    id: str
    map: str
    side: str
    grenade: str
    name: str
    stand: str
    aim: str
    throw_type: str
    throw: str
    covers: str
    stand_image: str
    aim_image: str
    setpos: str
    status: str
    notes: str = ""
    source_url: str = ""
    source_timestamp: str = ""
    second_source_url: str = ""
    verified_by_second_source: bool | None = None
    extra: dict = field(default_factory=dict)
    optional_keys: frozenset[str] = frozenset()

    def caption(self) -> str:
        """Stand spot, aim spot, and throw type, for the overlay."""

        base = f"{self.stand} → {self.aim}".strip()
        throw = self.throw_type.strip()
        if throw:
            return f"{base} ({throw})"
        return base

    def as_dict(self) -> dict:
        payload = {
            "id": self.id,
            "map": self.map,
            "side": self.side,
            "grenade": self.grenade,
            "name": self.name,
            "stand": self.stand,
            "aim": self.aim,
            "throw_type": self.throw_type,
            "throw": self.throw,
            "covers": self.covers,
            "stand_image": self.stand_image,
            "aim_image": self.aim_image,
            "setpos": self.setpos,
            "status": self.status,
        }
        for key in _OPTIONAL_STRINGS:
            if key in self.optional_keys:
                payload[key] = getattr(self, key)
        if _OPTIONAL_BOOL in self.optional_keys:
            payload[_OPTIONAL_BOOL] = self.verified_by_second_source
        payload.update(self.extra)
        return payload


@dataclass(frozen=True)
class LineupPack:
    version: int
    maps: tuple[str, ...]
    lineups: tuple[PackLineup, ...]
    extra: dict = field(default_factory=dict)
    unknown_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        payload = {
            "version": self.version,
            "maps": list(self.maps),
            "lineups": [item.as_dict() for item in self.lineups],
        }
        payload.update(self.extra)
        return payload


@dataclass(frozen=True)
class ImportResult:
    added: int
    replaced: int
    unknown_fields: tuple[str, ...] = ()


def note_extra_fields(
    names: Sequence[str],
    write: Callable[[str], None],
    *,
    seen: set[str],
) -> None:
    """Pass unknown field names to ``write`` once.

    ``seen`` remembers names already reported, including across later packs
    in the same window. Known optional fields are not included in ``names``.
    """

    fresh = [name for name in names if name not in seen]
    if not fresh:
        return
    seen.update(fresh)
    write("lineups: kept extra fields: " + ", ".join(fresh))


def parse_pack(raw: object) -> LineupPack:
    """Validate the JSON object. Does not look at image files."""

    if not isinstance(raw, dict):
        raise PackError("lineups.json must be a JSON object")
    version = raw.get("version")
    if version != PACK_VERSION:
        raise PackError(f"lineups.json version must be {PACK_VERSION}")
    maps_raw = raw.get("maps")
    if not isinstance(maps_raw, list) or not all(isinstance(item, str) and item.strip() for item in maps_raw):
        raise PackError("lineups.json maps must be a list of map names")
    rows = raw.get("lineups")
    if not isinstance(rows, list):
        raise PackError("lineups.json lineups must be a list")
    extra = {key: value for key, value in raw.items() if key not in _KNOWN_PACK}
    unknown = set(extra)
    lineups: list[PackLineup] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        lineup, names = _parse_lineup(row, index=index, seen=seen)
        unknown.update(names)
        lineups.append(lineup)
    return LineupPack(
        version=PACK_VERSION,
        maps=tuple(item.strip() for item in maps_raw),
        lineups=tuple(lineups),
        extra=extra,
        unknown_fields=tuple(sorted(unknown)),
    )


def load_pack_file(path: Path) -> LineupPack:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"Could not read {path.name}: {exc}") from exc
    return parse_pack(raw)


def validate_pack_dir(root: Path) -> LineupPack:
    """Parse lineups.json and require each photo to sit inside the pack."""

    pack_path = _find_pack_file(root)
    pack = load_pack_file(pack_path)
    base = pack_path.parent.resolve()
    for item in pack.lineups:
        _resolve_image(base, item.stand_image)
        _resolve_image(base, item.aim_image)
    return pack


def import_pack(source: Path, library: Path) -> ImportResult:
    """Copy a folder or zip into ``library``, replacing lineups that share an id."""

    source = Path(source)
    if source.is_file() and source.suffix.lower() == ".zip":
        return _import_zip(source, library)
    if source.is_dir():
        root = source if (source / PACK_FILENAME).is_file() else _find_pack_file(source).parent
        pack = validate_pack_dir(source)
        merged = _merge_pack(pack, root, library)
        return ImportResult(merged.added, merged.replaced, pack.unknown_fields)
    raise PackError("Choose a lineup pack folder or a .zip file")


def filter_lineups(
    pack: LineupPack,
    *,
    map_name: str | None = None,
    side: str | None = None,
    grenade: str | None = None,
    status: str | None = None,
) -> list[PackLineup]:
    """Lineups matching the browse filters. Blank or ``all`` leaves that filter open."""

    wanted_maps: set[str] | None = None
    if map_name and map_name.strip().lower() not in {"", "all"}:
        wanted_maps = {name.lower() for name in map_folder_names(map_name)}
    team: str | None = None
    if side and side.strip().lower() not in {"", "all"}:
        team = side.strip().upper()
        if team not in SIDES:
            return []
    kind: str | None = None
    if grenade and grenade.strip().lower() not in {"", "all"}:
        kind = grenade.strip().lower()
        if kind not in GRENADES:
            return []
    state: str | None = None
    if status and status.strip().lower() not in {"", "all"}:
        state = status.strip().lower()
        if state not in STATUSES:
            return []
    found: list[PackLineup] = []
    for item in pack.lineups:
        if wanted_maps is not None and item.map.strip().lower() not in wanted_maps:
            continue
        if team is not None and item.side != team:
            continue
        if kind is not None and item.grenade != kind:
            continue
        if state is not None and item.status != state:
            continue
        found.append(item)
    return found


def map_counts(pack: LineupPack) -> list[tuple[str, int]]:
    """Map names from the pack, in file order, each with how many lineups it has.

    A name in ``maps`` with no lineups is still listed. A lineup map missing
    from ``maps`` is appended.
    """

    counts: dict[str, int] = {}
    for item in pack.lineups:
        key = item.map.strip().lower()
        counts[key] = counts.get(key, 0) + 1
    listed: list[tuple[str, int]] = []
    seen: set[str] = set()
    for name in pack.maps:
        key = name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        listed.append((name.strip(), counts.get(key, 0)))
    for item in pack.lineups:
        key = item.map.strip().lower()
        if key not in seen:
            seen.add(key)
            listed.append((key, counts[key]))
    return listed


def pack_cards(
    library: Path,
    map_token: str | None = None,
    side: str | None = None,
    *,
    grenade: str | None = None,
    status: str | None = None,
) -> list[LineupCard]:
    """Imported lineups. Omit a filter to include every value of that field."""

    path = Path(library) / PACK_FILENAME
    if not path.is_file():
        return []
    try:
        pack = load_pack_file(path)
    except PackError:
        return []
    cards: list[LineupCard] = []
    root = path.parent
    for item in filter_lineups(pack, map_name=map_token, side=side, grenade=grenade, status=status):
        try:
            stand = _resolve_image(root, item.stand_image)
            aim = _resolve_image(root, item.aim_image)
        except PackError:
            continue
        cards.append(
            LineupCard(
                path=stand,
                caption=item.caption(),
                aim_path=aim,
                grenade=item.grenade,
                lineup_id=item.id,
                setpos=item.setpos,
                status=item.status,
                name=item.name,
                map_name=item.map,
                side=item.side,
                notes=item.notes,
                source_url=item.source_url,
            )
        )
    return cards


def _parse_lineup(row: object, *, index: int, seen: set[str]) -> tuple[PackLineup, set[str]]:
    label = f"lineups[{index}]"
    if not isinstance(row, dict):
        raise PackError(f"{label} must be an object")
    missing = [key for key in _REQUIRED if key not in row]
    if missing:
        raise PackError(f"{label} is missing {', '.join(missing)}")
    values = {key: row[key] for key in _REQUIRED}
    if any(not isinstance(value, str) for value in values.values()):
        raise PackError(f"{label} fields must be strings")
    optional = _optional_fields(row, label)
    lineup_id = values["id"].strip()
    if not lineup_id:
        raise PackError(f"{label}.id is empty")
    if lineup_id in seen:
        raise PackError(f"Duplicate lineup id {lineup_id}")
    seen.add(lineup_id)
    side = values["side"].strip()
    if side not in SIDES:
        raise PackError(f"{label}.side must be T or CT")
    grenade = values["grenade"].strip().lower()
    if grenade not in GRENADES:
        raise PackError(f"{label}.grenade must be smoke, flash, molotov, or he")
    status = values["status"].strip().lower()
    if status not in STATUSES:
        raise PackError(f"{label}.status must be draft or verified")
    map_name = values["map"].strip().lower()
    if not map_name:
        raise PackError(f"{label}.map is empty")
    extra = {key: row[key] for key in row if key not in _KNOWN_LINEUP}
    return (
        PackLineup(
            id=lineup_id,
            map=map_name,
            side=side,
            grenade=grenade,
            name=values["name"].strip(),
            stand=values["stand"].strip(),
            aim=values["aim"].strip(),
            throw_type=values["throw_type"].strip(),
            throw=values["throw"].strip(),
            covers=values["covers"].strip(),
            stand_image=_relative_image(values["stand_image"], label=f"{label}.stand_image"),
            aim_image=_relative_image(values["aim_image"], label=f"{label}.aim_image"),
            setpos=values["setpos"].strip(),
            status=status,
            notes=optional["notes"],
            source_url=optional["source_url"],
            source_timestamp=optional["source_timestamp"],
            second_source_url=optional["second_source_url"],
            verified_by_second_source=optional["verified_by_second_source"],
            extra=extra,
            optional_keys=optional["present"],
        ),
        set(extra),
    )


def _optional_fields(row: dict, label: str) -> dict:
    found: dict = {
        "notes": "",
        "source_url": "",
        "source_timestamp": "",
        "second_source_url": "",
        "verified_by_second_source": None,
        "present": frozenset(key for key in (*_OPTIONAL_STRINGS, _OPTIONAL_BOOL) if key in row),
    }
    for key in _OPTIONAL_STRINGS:
        if key not in row:
            continue
        value = row[key]
        if not isinstance(value, str):
            raise PackError(f"{label}.{key} must be a string")
        found[key] = value.strip()
    if _OPTIONAL_BOOL in row:
        value = row[_OPTIONAL_BOOL]
        if not isinstance(value, bool):
            raise PackError(f"{label}.{_OPTIONAL_BOOL} must be true or false")
        found[_OPTIONAL_BOOL] = value
    return found


def _relative_image(value: str, *, label: str) -> str:
    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith(".."):
        raise PackError(f"{label} must be a relative path inside the pack")
    parts = Path(raw).parts
    if ".." in parts:
        raise PackError(f"{label} must stay inside the pack")
    if Path(raw).suffix.lower() not in _IMAGE_SUFFIXES:
        raise PackError(f"{label} must be a png, jpg, or webp image")
    return raw


def _resolve_image(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PackError(f"{relative} escapes the pack") from exc
    if not path.is_file():
        raise PackError(f"Missing image {relative}")
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        raise PackError(f"{relative} is not an image")
    return path


def _find_pack_file(root: Path) -> Path:
    direct = root / PACK_FILENAME
    if direct.is_file():
        return direct
    nested = [path for path in root.glob(f"*/{PACK_FILENAME}") if path.is_file()]
    if len(nested) == 1:
        return nested[0]
    raise PackError("The pack needs a lineups.json file")


def _import_zip(source: Path, library: Path) -> ImportResult:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        dest = Path(folder)
        _safe_extract(source, dest)
        pack_file = _find_pack_file(dest)
        pack = validate_pack_dir(pack_file.parent)
        merged = _merge_pack(pack, pack_file.parent, library)
        return ImportResult(merged.added, merged.replaced, pack.unknown_fields)


def _safe_extract(source: Path, dest: Path) -> None:
    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise PackError("That file is not a zip pack") from exc
    with archive:
        for info in archive.infolist():
            relative = Path(info.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise PackError("The zip contains a path outside the pack")
            target = (dest / relative).resolve()
            try:
                target.relative_to(dest.resolve())
            except ValueError as exc:
                raise PackError("The zip contains a path outside the pack") from exc
        archive.extractall(dest)


def _merge_pack(pack: LineupPack, source_root: Path, library: Path) -> ImportResult:
    library.mkdir(parents=True, exist_ok=True)
    existing_path = library / PACK_FILENAME
    if existing_path.is_file():
        current = load_pack_file(existing_path)
        by_id = {item.id: item for item in current.lineups}
        maps = list(current.maps)
        extra = dict(current.extra)
    else:
        by_id = {}
        maps = []
        extra = {}
    extra.update(pack.extra)
    added = 0
    replaced = 0
    for item in pack.lineups:
        if item.id in by_id:
            replaced += 1
        else:
            added += 1
        by_id[item.id] = item
        _copy_image(source_root, library, item.stand_image)
        _copy_image(source_root, library, item.aim_image)
        if item.map not in maps:
            maps.append(item.map)
    merged = LineupPack(
        version=PACK_VERSION,
        maps=tuple(maps),
        lineups=tuple(by_id.values()),
        extra=extra,
    )
    payload = json.dumps(merged.as_dict(), indent=2) + "\n"
    temporary = existing_path.with_name(existing_path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(existing_path)
    return ImportResult(added=added, replaced=replaced)


def _copy_image(source_root: Path, library: Path, relative: str) -> None:
    source = _resolve_image(source_root, relative)
    target = (library / relative).resolve()
    try:
        target.relative_to(library.resolve())
    except ValueError as exc:
        raise PackError(f"{relative} escapes the lineup library") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
