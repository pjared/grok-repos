"""Smoke lineup trigger, library order, and hotkey clashes. No window and no images shipped."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config, parse_config
from suit_o.gsi.parse import parse_payload
from suit_o.gsi.payloads import make_payload
from suit_o.lineups.deck import LineupDeck
from suit_o.lineups.hotkeys import HotkeyError, assert_distinct, canonical_hotkey
from suit_o.lineups.library import import_image, list_cards, move_card, rename_card, set_caption
from suit_o.lineups.place import Monitor, place_overlay
from suit_o.gui.grenade_icons import ICON_ROWS
from suit_o.lineups.trigger import decide_overlay, held_grenade, is_smoke_grenade
from suit_o.preferences import save_lineup_settings

SMOKE = {"weapon_1": {"name": "weapon_smokegrenade", "state": "active", "ammo_reserve": 1}}
AWP = {
    "weapon_0": {"name": "weapon_awp", "state": "active", "ammo_clip": 5, "position": "9, 9, 9"},
    "weapon_1": {"name": "weapon_smokegrenade", "state": "holstered"},
}


def _png(path: Path, rgb: tuple[int, int, int] = (20, 120, 180)) -> None:
    width, height = 8, 4

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def _snap(**kwargs):
    snapshot = parse_payload(make_payload(**kwargs))
    assert snapshot is not None
    return snapshot


def test_active_smoke_is_kept_and_the_rest_of_the_loadout_is_not():
    snapshot = _snap(weapons=SMOKE)
    assert snapshot is not None
    assert snapshot.map_token == "de_dust2"
    assert snapshot.map_name == "dust2"
    assert snapshot.own is not None
    assert snapshot.own.active_weapon == "weapon_smokegrenade"
    blob = repr(snapshot)
    assert "ammo" not in blob
    assert "position" not in blob

    holding_awp = _snap(weapons=AWP)
    assert holding_awp.own is not None
    assert holding_awp.own.active_weapon == "weapon_awp"
    assert "smoke" not in repr(holding_awp.own.active_weapon)
    assert "9, 9, 9" not in repr(holding_awp)


def test_overlay_shows_only_while_alive_and_holding_a_smoke():
    shown = decide_overlay(
        map_key="de_dust2",
        side="ct",
        active_weapon="weapon_smokegrenade",
        health=100,
        round_phase="live",
        user_hidden=False,
    )
    assert shown.visible
    assert shown.reason == "smoke"
    assert shown.grenade == "smoke"
    assert is_smoke_grenade("weapon_smokegrenade")
    assert not is_smoke_grenade("weapon_flashbang")
    assert held_grenade("weapon_smokegrenade") == "smoke"
    assert held_grenade("weapon_flashbang") == "flash"
    assert held_grenade("weapon_molotov") == "molotov"
    assert held_grenade("weapon_incgrenade") == "molotov"
    assert held_grenade("weapon_hegrenade") == "he"
    assert held_grenade("weapon_awp") is None
    flash = decide_overlay(
        map_key="de_mirage",
        side="t",
        active_weapon="weapon_flashbang",
        health=100,
        round_phase="live",
        user_hidden=False,
    )
    assert flash.visible
    assert flash.reason == "flash"
    assert flash.grenade == "flash"

    hidden_rifle = decide_overlay(
        map_key="de_dust2",
        side="ct",
        active_weapon="weapon_awp",
        health=100,
        round_phase="live",
        user_hidden=False,
    )
    assert hidden_rifle.visible is False
    assert hidden_rifle.reason == "not-grenade"
    assert (
        decide_overlay(
            map_key="de_dust2",
            side="ct",
            active_weapon="weapon_smokegrenade",
            health=0,
            round_phase="live",
            user_hidden=False,
        ).reason
        == "dead"
    )
    assert (
        decide_overlay(
            map_key="de_dust2",
            side="ct",
            active_weapon="weapon_smokegrenade",
            health=None,
            round_phase="live",
            user_hidden=False,
        ).reason
        == "dead"
    )
    assert (
        decide_overlay(
            map_key="de_dust2",
            side="t",
            active_weapon="weapon_smokegrenade",
            health=80,
            round_phase="over",
            user_hidden=False,
        ).reason
        == "round-over"
    )
    assert (
        decide_overlay(
            map_key="de_mirage",
            side="t",
            active_weapon="weapon_smokegrenade",
            health=80,
            round_phase="freezetime",
            user_hidden=True,
        ).reason
        == "hidden"
    )


def test_deck_follows_gsi_and_cycles_in_saved_order(tmp_path: Path):
    folder = tmp_path / "de_dust2" / "ct"
    folder.mkdir(parents=True)
    for name, color in (("bravo.png", (10, 10, 200)), ("alpha.png", (200, 10, 10)), ("charlie.png", (10, 200, 10))):
        _png(folder / name, color)
    (folder / "alpha.txt").write_text("Xbox smoke\n", encoding="utf-8")
    (folder / "order.txt").write_text("charlie.png\nalpha.png\nbravo.png\n", encoding="utf-8")

    cards = list_cards(tmp_path, "de_dust2", "CT")
    assert [card.filename for card in cards] == ["charlie.png", "alpha.png", "bravo.png"]
    assert cards[1].caption == "Xbox smoke"
    assert cards[0].caption == "charlie"

    moved = move_card(tmp_path, "de_dust2", "ct", "alpha.png", -1)
    assert [card.filename for card in moved] == ["alpha.png", "charlie.png", "bravo.png"]

    renamed = rename_card(moved[0], "A long smoke")
    assert renamed.path.name == "a_long_smoke.png"
    recaptioned = set_caption(renamed, "From xbox")
    assert recaptioned.caption == "From xbox"

    deck = LineupDeck(tmp_path)
    hidden = deck.observe(_snap(team="CT", weapons=AWP, health=100, round_phase="live"))
    assert hidden.visible is False
    assert hidden.reason == "not-grenade"

    shown = deck.observe(_snap(team="CT", weapons=SMOKE, health=100, round_phase="live", map_name="de_dust2"))
    assert shown.visible
    assert shown.side == "ct"
    assert shown.total == 3
    first = shown.card
    assert first is not None
    nxt = deck.cycle(1)
    assert nxt.card is not None
    assert nxt.card.filename != first.filename
    wrapped = deck.cycle(1)
    deck.cycle(1)
    assert wrapped.card is not None
    again = deck.view()
    assert again.card is not None
    assert again.card.filename == first.filename

    dead = deck.observe(_snap(team="CT", weapons=SMOKE, health=0, round_phase="live"))
    assert dead.visible is False
    assert dead.reason == "dead"
    over = deck.observe(_snap(team="CT", weapons=SMOKE, health=100, round_phase="over"))
    assert over.reason == "round-over"
    toggled = deck.toggle()
    assert toggled.hidden
    back = deck.observe(_snap(team="CT", weapons=SMOKE, health=100, round_phase="live"))
    assert back.reason == "hidden"
    assert deck.toggle().hidden is False


def test_short_map_folder_matches_the_cs2_name(tmp_path: Path):
    folder = tmp_path / "dust2" / "t"
    folder.mkdir(parents=True)
    source = tmp_path / "shot.png"
    _png(source)
    imported = import_image(tmp_path, "de_dust2", "T", source)
    assert imported.path.parent == folder
    cards = list_cards(tmp_path, "de_dust2", "t")
    assert len(cards) == 1
    assert cards[0].caption == "shot"


def test_hotkeys_must_differ_from_voice_and_each_other():
    assert canonical_hotkey("Ctrl + Shift + Right") == "ctrl+shift+right"
    assert_distinct(
        ["ctrl+shift+right", "ctrl+shift+left", "ctrl+shift+h"],
        voice_key="v",
        ptt_key="",
    )
    try:
        assert_distinct(["v"], voice_key="V", ptt_key="")
        clashed = False
    except HotkeyError as exc:
        clashed = True
        assert "voice" in str(exc).lower()
    assert clashed

    raw = __import__("yaml").safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["lineups"]["hotkey_next"] = "v"
    try:
        parse_config(raw)
        raised = False
    except ConfigError as exc:
        raised = True
        assert "voice" in str(exc).lower()
    assert raised

    config = load_config(DEFAULT_CONFIG_PATH)
    assert config.lineups.corner == "top-right"
    assert config.lineups.hotkey_next == "ctrl+shift+right"
    assert config.lineups.enabled is True


def test_overlay_sits_in_the_requested_corner():
    monitor = Monitor(0, 100, 50, 800, 600, "Primary")
    assert place_overlay(monitor, "top-right", 200, 100) == (100 + 800 - 200 - 16, 50 + 16)
    assert place_overlay(monitor, "bottom-left", 200, 100) == (100 + 16, 50 + 600 - 100 - 16)


def test_grenade_icons_are_original_drawings():
    assert set(ICON_ROWS) == {"smoke", "flash", "molotov", "he"}
    glyphs = []
    for rows in ICON_ROWS.values():
        assert len(rows) == 16
        assert all(len(row) == 16 for row in rows)
        glyphs.append(rows)
    assert len(set(glyphs)) == 4


def test_lineup_settings_round_trip_without_touching_speech(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    before_speech = "backend: pyttsx3"
    save_lineup_settings(
        path,
        width=400,
        opacity=0.5,
        corner="bottom-left",
        hotkey_next="ctrl+alt+right",
        hotkey_previous="ctrl+alt+left",
        hotkey_toggle="ctrl+alt+h",
        voice_key="v",
        ptt_key="",
    )
    text = path.read_text(encoding="utf-8")
    assert before_speech in text
    assert "Do not set a microphone" in text
    saved = load_config(path)
    assert saved.lineups.width == 400
    assert saved.lineups.opacity == 0.5
    assert saved.lineups.corner == "bottom-left"
    assert saved.lineups.hotkey_next == "ctrl+alt+right"
    assert saved.speech.backend == "pyttsx3"
