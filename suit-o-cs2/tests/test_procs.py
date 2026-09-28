"""Helper commands never open a console window on Windows."""

from __future__ import annotations

import subprocess
from pathlib import Path

from suit_o import update
from suit_o.procs import hidden_window_kwargs
from suit_o.voice import ffmpeg


def test_windows_children_get_no_window_and_other_platforms_get_nothing():
    assert hidden_window_kwargs("win32") == {"creationflags": 0x08000000}
    assert hidden_window_kwargs("linux") == {}
    assert hidden_window_kwargs("darwin") == {}


def test_update_and_ffmpeg_pass_the_no_window_flag(tmp_path: Path, monkeypatch):
    seen: list[dict] = []

    class _Done:
        returncode = 0
        stdout = ""
        stderr = b"Duration: 00:00:01.50, start"

    def run(args, **kwargs):
        seen.append(kwargs)
        return _Done()

    monkeypatch.setattr("suit_o.procs.sys.platform", "win32")
    monkeypatch.setattr(subprocess, "run", run)
    update.subprocess_runner(["git", "status"], tmp_path)
    assert seen[-1]["creationflags"] == 0x08000000

    source = tmp_path / "take.wav"
    source.write_bytes(b"RIFF")
    monkeypatch.setattr(ffmpeg, "require_ffmpeg", lambda: "ffmpeg")
    assert ffmpeg.probe_duration(source) == 1.5
    assert seen[-1]["creationflags"] == 0x08000000
