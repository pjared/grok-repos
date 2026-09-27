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


def test_ui_queue_logs_a_callback_error_and_keeps_the_rest(caplog):
    ran: list[str] = []

    def broken() -> None:
        raise RuntimeError("window update broke")

    ui = UiQueue()
    ui.call(broken)
    ui.call(lambda: ran.append("after"))
    with caplog.at_level("ERROR"):
        ui.drain()
    assert ran == ["after"]
    assert "window update broke" in caplog.text
    ui.call(lambda: ran.append("later"))
    ui.drain()
    assert ran == ["after", "later"]


def test_ui_queue_pump_keeps_running_after_a_callback_error():
    import tkinter as tk

    from tkutil import open_tk_or_skip

    root = open_tk_or_skip()
    ran: list[str] = []
    try:
        ui = UiQueue()
        ui.bind(root)

        def broken() -> None:
            raise tk.TclError("one widget was already gone")

        ui.call(broken)
        root.update()
        root.after(40, lambda: ui.call(lambda: ran.append("alive")))
        root.after(100, root.quit)
        root.mainloop()
        assert ran == ["alive"]
    finally:
        root.destroy()
