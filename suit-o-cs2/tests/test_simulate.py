"""The simulator must produce a stubbed line for every event."""

from __future__ import annotations

from suit_o.simulate import main


def test_simulator_triggers_every_event(capsys):
    code = main([])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "All 19 events produced a line." in captured.out
    assert "9999" not in captured.out
