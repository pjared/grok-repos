"""UI work stays queued until the main thread drains it."""

from __future__ import annotations

from suit_o.gui.ui_queue import UiQueue


def test_ui_queue_runs_callbacks_on_drain_not_on_call():
    ran: list[str] = []
    ui = UiQueue()
    ui.call(lambda: ran.append("one"))
    ui.call(lambda: ran.append("two"))
    assert ran == []
    ui.drain()
    assert ran == ["one", "two"]
    ui.drain()
    assert ran == ["one", "two"]
