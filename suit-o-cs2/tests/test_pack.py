"""Lineup pack schema, import, and the smokes-only overlay filter."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from suit_o.config import PROJECT_ROOT
from suit_o.gsi.payloads import make_payload
from suit_o.gsi.parse import parse_payload
from suit_o.gui.overlay import overlay_images
from suit_o.lineups.deck import LineupDeck
from suit_o.lineups.library import LineupCard
from suit_o.lineups.pack import (
    PackError,
    filter_lineups,
    import_pack,
    load_pack_file,
    map_counts,
    note_extra_fields,
    pack_cards,
    parse_pack,
)

EXAMPLE = PROJECT_ROOT / "lineups" / "example-pack" / "lineups.json"
SCHEMA = PROJECT_ROOT / "lineups" / "pack.schema.json"


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    )


def _row(**overrides) -> dict:
    base = json.loads(EXAMPLE.read_text(encoding="utf-8"))["lineups"][0]
    base.update(overrides)
    return base


def _snap(**kwargs):
    snapshot = parse_payload(make_payload(**kwargs))
    assert snapshot is not None
    return snapshot


def test_schema_and_example_describe_version_one_without_images():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert schema["properties"]["version"]["const"] == 1
    required = schema["$defs"]["lineup"]["required"]
    assert schema["required"] == ["version", "maps", "lineups"]
    assert list(example) == ["version", "maps", "lineups"]
    assert required == [
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
    ]
    assert set(example["lineups"][0]) == set(required)
    optional = schema["$defs"]["lineup"]["properties"]
    assert optional["notes"] == {"type": ["string", "null"]}
    assert optional["source_url"] == {"type": ["string", "null"]}
    assert optional["source_timestamp"] == {"type": ["string", "null"]}
    assert optional["second_source_url"] == {"type": ["string", "null"]}
    assert optional["verified_by_second_source"] == {"type": ["boolean", "null"]}
    for key in (
        "notes",
        "source_url",
        "source_timestamp",
        "second_source_url",
        "verified_by_second_source",
    ):
        assert key not in required
    pack = parse_pack(example)
    assert pack.unknown_fields == ()
    assert pack.as_dict() == example
    assert pack.version == 1
    assert pack.maps == ("mirage",)
    lineup = pack.lineups[0]
    assert lineup.id == "mirage-t-smoke-window-example"
    assert lineup.caption() == "T ramp → Window (jumpthrow)"
    assert lineup.setpos.startswith("setpos ")
    assert list(EXAMPLE.parent.rglob("*.png")) == []
    assert load_pack_file(EXAMPLE).lineups[0].grenade == "smoke"


def test_parse_rejects_a_bad_version_side_duplicate_or_escaping_path():
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    example["version"] = 2
    try:
        parse_pack(example)
    except PackError as exc:
        assert "version" in str(exc)
    else:
        raise AssertionError("version 2 was accepted")

    bad_side = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad_side["lineups"][0]["side"] = "t"
    try:
        parse_pack(bad_side)
    except PackError as exc:
        assert "side" in str(exc)
    else:
        raise AssertionError("lowercase side was accepted")

    duplicated = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    duplicated["lineups"].append(dict(duplicated["lineups"][0]))
    try:
        parse_pack(duplicated)
    except PackError as exc:
        assert "Duplicate" in str(exc)
    else:
        raise AssertionError("a duplicate id was accepted")

    bad_status = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad_status["lineups"][0]["status"] = "ready"
    try:
        parse_pack(bad_status)
    except PackError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("status ready was accepted")

    bad_grenade = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad_grenade["lineups"][0]["grenade"] = "incendiary"
    try:
        parse_pack(bad_grenade)
    except PackError as exc:
        assert "grenade" in str(exc)
    else:
        raise AssertionError("grenade incendiary was accepted")

    escaped = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    escaped["lineups"][0]["stand_image"] = "../secret.png"
    try:
        parse_pack(escaped)
    except PackError as exc:
        assert "relative" in str(exc)
    else:
        raise AssertionError("a path outside the pack was accepted")


def test_folder_and_zip_import_merge_by_id_and_stay_in_the_library(tmp_path: Path):
    source = tmp_path / "pack"
    _png(source / "images" / "window-stand.png")
    _png(source / "images" / "window-aim.png")
    _png(source / "images" / "connector-stand.png")
    _png(source / "images" / "connector-aim.png")
    flash_stand = source / "images" / "flash-stand.png"
    flash_aim = source / "images" / "flash-aim.png"
    _png(flash_stand)
    _png(flash_aim)
    _png(source / "images" / "molotov-stand.png")
    _png(source / "images" / "molotov-aim.png")
    _png(source / "images" / "he-stand.png")
    _png(source / "images" / "he-aim.png")
    document = {
        "version": 1,
        "maps": ["mirage"],
        "lineups": [
            _row(),
            _row(
                id="mirage-ct-smoke-connector",
                side="CT",
                name="Connector",
                stand="CT spawn",
                aim="Connector",
                throw_type="run-throw",
                stand_image="images/connector-stand.png",
                aim_image="images/connector-aim.png",
            ),
            _row(
                id="mirage-t-flash-ramp",
                grenade="flash",
                name="Ramp flash",
                stand="T ramp",
                aim="Jungle",
                throw_type="jumpthrow",
                stand_image="images/flash-stand.png",
                aim_image="images/flash-aim.png",
                status="verified",
            ),
            _row(
                id="mirage-t-molotov-ramp",
                grenade="molotov",
                name="Ramp molotov",
                stand="T ramp",
                aim="Palace",
                throw_type="jumpthrow",
                stand_image="images/molotov-stand.png",
                aim_image="images/molotov-aim.png",
            ),
            _row(
                id="mirage-t-he-ramp",
                grenade="he",
                name="Ramp HE",
                stand="T ramp",
                aim="Default",
                throw_type="throw",
                stand_image="images/he-stand.png",
                aim_image="images/he-aim.png",
            ),
        ],
    }
    (source / "lineups.json").write_text(json.dumps(document), encoding="utf-8")
    library = tmp_path / "lineup-data"
    first = import_pack(source, library)
    assert (first.added, first.replaced) == (5, 0)
    assert (library / "lineups.json").is_file()
    assert (library / "images" / "window-stand.png").is_file()
    assert not (PROJECT_ROOT / "lineup-data" / "images").exists()

    archive = tmp_path / "again.zip"
    replacement = json.loads(json.dumps(document))
    replacement["lineups"] = [
        _row(name="Window smoke revised", stand="T ramp boxes", aim="Window left")
    ]
    nested = tmp_path / "nested"
    _png(nested / "images" / "window-stand.png")
    _png(nested / "images" / "window-aim.png")
    (nested / "lineups.json").write_text(json.dumps(replacement), encoding="utf-8")
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in nested.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(nested).as_posix())
    second = import_pack(archive, library)
    assert (second.added, second.replaced) == (0, 1)
    saved = load_pack_file(library / "lineups.json")
    by_id = {item.id: item for item in saved.lineups}
    assert set(by_id) == {
        "mirage-t-smoke-window-example",
        "mirage-ct-smoke-connector",
        "mirage-t-flash-ramp",
        "mirage-t-molotov-ramp",
        "mirage-t-he-ramp",
    }
    assert by_id["mirage-t-smoke-window-example"].stand == "T ramp boxes"
    assert by_id["mirage-t-smoke-window-example"].caption() == "T ramp boxes → Window left (jumpthrow)"

    slipped = tmp_path / "slip.zip"
    with zipfile.ZipFile(slipped, "w") as zipped:
        zipped.writestr("../outside.txt", "nope")
    try:
        import_pack(slipped, library)
    except PackError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("a zip slip was accepted")
    assert not (tmp_path / "outside.txt").exists()

    smokes = pack_cards(library, "de_mirage", "t", grenade="smoke")
    assert [card.lineup_id for card in smokes] == ["mirage-t-smoke-window-example"]
    assert smokes[0].aim_path is not None
    assert smokes[0].aim_path.is_file()
    assert smokes[0].setpos.startswith("setpos ")
    assert smokes[0].status == "draft"
    assert smokes[0].name == "Window smoke revised"
    everything = pack_cards(library, "de_mirage", "T")
    assert {card.grenade for card in everything} == {"smoke", "flash", "molotov", "he"}
    assert pack_cards(library, "de_mirage", "ct", grenade="smoke")[0].caption == (
        "CT spawn → Connector (run-throw)"
    )

    def holding(weapon: str):
        return _snap(team="T", map_name="de_mirage", round_phase="live", health=100, weapons={
            "weapon_1": {"name": weapon, "state": "active"},
        })

    deck = LineupDeck(tmp_path / "folder-images", pack_dir=library)
    shown = deck.observe(holding("weapon_smokegrenade"))
    assert shown.visible
    assert shown.total == 1
    assert shown.card is not None
    assert shown.card.lineup_id == "mirage-t-smoke-window-example"
    assert shown.card.setpos.startswith("setpos ")
    assert "setpos" not in shown.reason
    slots = overlay_images(shown.card, 320)
    assert [slot[1] for slot in slots] == [160, 160]
    assert slots[0][0] == shown.card.path
    assert slots[1][0] == shown.card.aim_path

    deck.set_smokes_only(False)
    still_smoke = deck.observe(holding("weapon_smokegrenade"))
    assert still_smoke.total == 1
    assert still_smoke.card is not None
    assert still_smoke.card.grenade == "smoke"

    flashed = deck.observe(holding("weapon_flashbang"))
    assert flashed.visible
    assert flashed.total == 1
    assert flashed.card is not None
    assert flashed.card.lineup_id == "mirage-t-flash-ramp"
    assert flashed.reason == "flash"

    burned = deck.observe(holding("weapon_incgrenade"))
    assert burned.card is not None
    assert burned.card.lineup_id == "mirage-t-molotov-ramp"
    same = deck.observe(holding("weapon_molotov"))
    assert same.card is not None
    assert same.card.grenade == "molotov"

    exploded = deck.observe(holding("weapon_hegrenade"))
    assert exploded.card is not None
    assert exploded.card.lineup_id == "mirage-t-he-ramp"

    lone = overlay_images(LineupCard(path=flash_stand, caption="only stand"), 300)
    assert lone == [(flash_stand, 300)]


def test_filters_and_map_counts_follow_the_pack_document():
    pack = parse_pack(
        {
            "version": 1,
            "maps": ["mirage", "inferno", "ancient"],
            "lineups": [
                _row(),
                _row(
                    id="mirage-ct-flash",
                    side="CT",
                    grenade="flash",
                    status="verified",
                    name="CT flash",
                ),
                _row(
                    id="inferno-t-molotov",
                    map="inferno",
                    grenade="molotov",
                    status="verified",
                ),
                _row(id="inferno-t-he", map="inferno", grenade="he", status="draft"),
                _row(id="nuke-t-smoke", map="nuke", grenade="smoke", status="draft"),
            ],
        }
    )
    assert map_counts(pack) == [("mirage", 2), ("inferno", 2), ("ancient", 0), ("nuke", 1)]
    assert [item.id for item in filter_lineups(pack, map_name="de_mirage")] == [
        "mirage-t-smoke-window-example",
        "mirage-ct-flash",
    ]
    assert [item.id for item in filter_lineups(pack, side="CT")] == ["mirage-ct-flash"]
    assert [item.id for item in filter_lineups(pack, grenade="he")] == ["inferno-t-he"]
    assert [item.id for item in filter_lineups(pack, status="verified")] == [
        "mirage-ct-flash",
        "inferno-t-molotov",
    ]
    assert [item.id for item in filter_lineups(pack, map_name="inferno", side="T", grenade="molotov", status="verified")] == [
        "inferno-t-molotov",
    ]
    assert filter_lineups(pack, map_name="ancient") == []
    assert len(filter_lineups(pack)) == 5


def test_null_source_timestamp_imports_as_missing():
    row = _row(source_timestamp=None)
    pack = parse_pack({"version": 1, "maps": ["mirage"], "lineups": [row]})
    lineup = pack.lineups[0]
    assert lineup.source_timestamp == ""
    assert "source_timestamp" not in lineup.optional_keys
    assert "source_timestamp" not in lineup.as_dict()


def test_unknown_fields_are_kept_and_logged_once(tmp_path: Path):
    first = _row(
        notes="Stand on the box.",
        source_url="https://example.com/window",
        source_timestamp="1:05",
        second_source_url="https://example.com/second",
        verified_by_second_source=True,
        editor="ada",
    )
    second = _row(
        id="mirage-ct-smoke-connector",
        side="CT",
        name="Connector",
        stand="CT spawn",
        aim="Connector",
        stand_image="images/connector-stand.png",
        aim_image="images/connector-aim.png",
        notes="",
        verified_by_second_source=False,
        editor="ada",
        future_flag={"ok": True},
    )
    document = {
        "version": 1,
        "maps": ["mirage"],
        "lineups": [first, second],
        "generator": "mirage-pack",
    }
    pack = parse_pack(document)
    assert pack.unknown_fields == ("editor", "future_flag", "generator")
    lineup = pack.lineups[0]
    assert lineup.notes == "Stand on the box."
    assert lineup.source_url == "https://example.com/window"
    assert lineup.source_timestamp == "1:05"
    assert lineup.second_source_url == "https://example.com/second"
    assert lineup.verified_by_second_source is True
    assert lineup.extra == {"editor": "ada"}
    assert pack.lineups[1].notes == ""
    assert pack.lineups[1].verified_by_second_source is False
    assert pack.lineups[1].extra["future_flag"] == {"ok": True}
    assert pack.extra == {"generator": "mirage-pack"}
    assert parse_pack(pack.as_dict()).as_dict() == pack.as_dict()

    messages: list[str] = []
    seen: set[str] = set()
    note_extra_fields(pack.unknown_fields, messages.append, seen=seen)
    note_extra_fields(pack.unknown_fields, messages.append, seen=seen)
    note_extra_fields(("editor", "newer"), messages.append, seen=seen)
    assert messages == [
        "lineups: kept extra fields: editor, future_flag, generator",
        "lineups: kept extra fields: newer",
    ]

    missing = _row()
    del missing["aim"]
    try:
        parse_pack({"version": 1, "maps": ["mirage"], "lineups": [missing], "generator": "x"})
    except PackError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("a lineup missing aim was accepted")

    bad_notes = _row(notes=3)
    try:
        parse_pack({"version": 1, "maps": ["mirage"], "lineups": [bad_notes]})
    except PackError as exc:
        assert "notes" in str(exc)
    else:
        raise AssertionError("a numeric notes field was accepted")

    bad_flag = _row(verified_by_second_source="yes")
    try:
        parse_pack({"version": 1, "maps": ["mirage"], "lineups": [bad_flag]})
    except PackError as exc:
        assert "verified_by_second_source" in str(exc)
    else:
        raise AssertionError("a string flag was accepted")

    source = tmp_path / "pack"
    _png(source / "images" / "window-stand.png")
    _png(source / "images" / "window-aim.png")
    _png(source / "images" / "connector-stand.png")
    _png(source / "images" / "connector-aim.png")
    (source / "lineups.json").write_text(json.dumps(document), encoding="utf-8")
    library = tmp_path / "lineup-data"
    imported = import_pack(source, library)
    assert imported.unknown_fields == ("editor", "future_flag", "generator")
    saved = json.loads((library / "lineups.json").read_text(encoding="utf-8"))
    assert saved["generator"] == "mirage-pack"
    assert saved["lineups"][0]["notes"] == "Stand on the box."
    assert saved["lineups"][0]["source_url"] == "https://example.com/window"
    assert saved["lineups"][0]["editor"] == "ada"
    assert saved["lineups"][1]["notes"] == ""
    assert saved["lineups"][1]["verified_by_second_source"] is False
    assert saved["lineups"][1]["future_flag"] == {"ok": True}

    follow = {
        "version": 1,
        "maps": ["mirage"],
        "lineups": [_row(id="mirage-t-flash-ramp", grenade="flash", name="Ramp flash")],
        "reviewed": True,
    }
    follow_dir = tmp_path / "follow"
    _png(follow_dir / "images" / "window-stand.png")
    _png(follow_dir / "images" / "window-aim.png")
    (follow_dir / "lineups.json").write_text(json.dumps(follow), encoding="utf-8")
    import_pack(follow_dir, library)
    merged = json.loads((library / "lineups.json").read_text(encoding="utf-8"))
    assert merged["generator"] == "mirage-pack"
    assert merged["reviewed"] is True
    by_id = {item["id"]: item for item in merged["lineups"]}
    assert by_id["mirage-t-smoke-window-example"]["source_timestamp"] == "1:05"
    assert by_id["mirage-t-flash-ramp"]["grenade"] == "flash"
    cards = pack_cards(library, "mirage", "T")
    window = next(card for card in cards if card.lineup_id == "mirage-t-smoke-window-example")
    assert window.notes == "Stand on the box."
    assert window.source_url == "https://example.com/window"


def test_detail_view_shows_notes_and_the_source_link(tmp_path: Path):
    from tkinter import ttk

    from suit_o.config import LineupConfig
    from suit_o.gui.lineups import LineupsPanel
    from tkutil import open_tk_or_skip

    source = tmp_path / "pack"
    _png(source / "images" / "window-stand.png")
    _png(source / "images" / "window-aim.png")
    document = {
        "version": 1,
        "maps": ["mirage"],
        "lineups": [
            _row(
                notes="Stand on the box.",
                source_url="https://example.com/window",
                editor="ada",
            ),
            _row(
                id="mirage-t-flash-ramp",
                grenade="flash",
                name="Ramp flash",
                editor="ada",
                notes="Throw from ramp.",
                source_url="https://example.com/flash",
            ),
        ],
        "generator": "mirage-pack",
    }
    (source / "lineups.json").write_text(json.dumps(document), encoding="utf-8")

    class _Config:
        lineups = LineupConfig()

    class _App:
        def __init__(self) -> None:
            self.config = _Config()
            self.pack_dir = tmp_path / "lineup-data"
            self.lineups_dir = tmp_path / "lineups"
            self.messages: list[str] = []

        def note(self, message: str) -> None:
            self.messages.append(message)

    root = open_tk_or_skip()
    try:
        app = _App()
        panel = LineupsPanel(ttk.Frame(root), app, on_saved=lambda: None)
        panel.import_pack_from(source)
        root.update_idletasks()
        assert app.messages == ["lineups: kept extra fields: editor, generator"]
        assert panel.notes_label.cget("text") == "Stand on the box."
        assert panel.source_link.cget("text") == "https://example.com/window"
        assert panel._source_url == "https://example.com/window"
        panel.cards.selection_set("1")
        panel._show_selected()
        assert panel.notes_label.cget("text") == "Throw from ramp."
        assert panel.source_link.cget("text") == "https://example.com/flash"
        panel.import_pack_from(source)
        assert app.messages == ["lineups: kept extra fields: editor, generator"]
    finally:
        root.destroy()
