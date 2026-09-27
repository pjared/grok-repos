"""The simulator must produce a stubbed line for every event."""

from __future__ import annotations

from suit_o.simulate import main


def test_menu_scenario_greets_once(capsys):
    code = main(["--menu"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.out.count("[menu_greeting]") == 1
    assert "Main-menu greeting spoken once." in captured.out
    assert any(phrase in captured.out for phrase in ("Premier", "Ready to queue?"))


def test_simulator_triggers_every_event(capsys):
    code = main([])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "All 20 events produced a line." in captured.out
    assert "9999" not in captured.out
