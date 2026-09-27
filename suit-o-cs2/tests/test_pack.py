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
    import_pack,
    load_pack_file,
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
    assert "version" in schema["required"]
    assert set(example["lineups"][0]) == set(required)
    pack = parse_pack(example)
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

    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    example["extra"] = True
    try:
        parse_pack(example)
    except PackError as exc:
        assert "unexpected" in str(exc)
    else:
        raise AssertionError("an extra pack field was accepted")

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
            ),
        ],
    }
    (source / "lineups.json").write_text(json.dumps(document), encoding="utf-8")
    library = tmp_path / "lineup-data"
    first = import_pack(source, library)
    assert (first.added, first.replaced) == (3, 0)
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

    smokes = pack_cards(library, "de_mirage", "t", smokes_only=True)
    assert [card.lineup_id for card in smokes] == ["mirage-t-smoke-window-example"]
    assert smokes[0].aim_path is not None
    assert smokes[0].aim_path.is_file()
    everything = pack_cards(library, "de_mirage", "T", smokes_only=False)
    assert {card.grenade for card in everything} == {"smoke", "flash"}
    assert pack_cards(library, "de_mirage", "ct", smokes_only=True)[0].caption == (
        "CT spawn → Connector (run-throw)"
    )

    deck = LineupDeck(tmp_path / "folder-images", pack_dir=library)
    deck.set_smokes_only(True)
    shown = deck.observe(
        _snap(team="T", map_name="de_mirage", round_phase="live", health=100, weapons={
            "weapon_1": {"name": "weapon_smokegrenade", "state": "active"},
        })
    )
    assert shown.visible
    assert shown.total == 1
    assert shown.card is not None
    assert shown.card.lineup_id == "mirage-t-smoke-window-example"
    slots = overlay_images(shown.card, 320)
    assert [slot[1] for slot in slots] == [160, 160]
    assert slots[0][0] == shown.card.path
    assert slots[1][0] == shown.card.aim_path

    deck.set_smokes_only(False)
    both = deck.observe(
        _snap(team="T", map_name="de_mirage", round_phase="live", health=100, weapons={
            "weapon_1": {"name": "weapon_smokegrenade", "state": "active"},
        })
    )
    assert both.total == 2

    lone = overlay_images(LineupCard(path=flash_stand, caption="only stand"), 300)
    assert lone == [(flash_stand, 300)]
