"""Status lines for the desktop window. These do not open a display."""

from __future__ import annotations

import time

from suit_o.app import Activity
from suit_o.gui.status import (
    device_menu_labels,
    format_activity,
    format_age,
    format_game_state,
    format_listener,
    format_sound,
    selected_device_label,
)
from suit_o.speech.devices import WINDOWS_DEFAULT_LABEL

GAME = "Speakers (Example Headset Game)"
CHAT = "Headset Earphone (Example Chat)"
REALTEK = "Realtek Digital Output"
MONITOR = "Monitor (Example Display)"


def test_listener_and_game_state_wording():
    assert format_listener(True, "127.0.0.1", 3000) == (
        "Listener up · http://127.0.0.1:3000",
        "ok",
    )
    assert format_listener(False, "127.0.0.1", 3000)[1] == "down"
    assert format_game_state(None) == ("Waiting for CS2", "wait")
    fresh, tone = format_game_state(3, received=12)
    assert tone == "ok"
    assert "CS2 is sending game state" in fresh
    assert "3s ago" in fresh
    assert "12 received" in fresh
    stale, stale_tone = format_game_state(90, received=4)
    assert stale_tone == "stale"
    assert "No recent game state" in stale
    assert "1m 30s ago" in stale
    assert format_age(3661) == "1h 1m"
    assert format_sound(True)[1] == "muted"
    assert format_sound(False) == ("Sound on", "ok")


def test_device_menu_keeps_the_default_and_a_missing_saved_name():
    names = [GAME, CHAT, REALTEK, MONITOR]
    labels = device_menu_labels(names, "")
    assert labels[0] == WINDOWS_DEFAULT_LABEL
    assert all("microphone" not in label.lower() for label in labels)
    assert selected_device_label("", names) == WINDOWS_DEFAULT_LABEL
    assert selected_device_label("chat", names) == CHAT
    unplugged = device_menu_labels(names, "Old Headset")
    assert unplugged[-1] == "Old Headset"
    assert selected_device_label("Old Headset", names) == "Old Headset"


def test_activity_line_uses_local_time():
    moment = time.time()
    entry = Activity(seq=1, at=moment, message="death: goodbye")
    text = format_activity(entry)
    assert text.endswith("  death: goodbye")
    assert text.startswith(time.strftime("%H:%M:%S", time.localtime(moment)))
