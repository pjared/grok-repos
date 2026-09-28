"""The Installations window and the header button that hides itself. Tk only, no installs."""

from __future__ import annotations

from tkutil import open_tk_or_skip

from suit_o.gui.installs import INSTALLED, NEEDS_311, NOT_INSTALLED, InstallsWindow
from suit_o.installs.components import CommandResult, Probes, Step


def _probes(**installed: bool) -> Probes:
    return Probes(
        chat=lambda: installed.get("chat", False),
        voice=lambda: installed.get("voice", False),
        clips=lambda: installed.get("clips", False),
        ollama=lambda: installed.get("ollama", False),
    )


def test_rows_show_status_and_lock_installed_or_blocked_parts():
    root = open_tk_or_skip()
    try:
        panel = InstallsWindow(
            root,
            schedule=lambda callback: callback(),
            probes=_probes(ollama=True),
            python_version=(3, 14),
            threaded=False,
        )
        assert panel.states["ollama"].cget("text") == INSTALLED
        assert panel.states["chat"].cget("text") == NOT_INSTALLED
        assert panel.states["voice"].cget("text") == NEEDS_311
        assert panel.states["clips"].cget("text") == NEEDS_311
        assert "disabled" in panel.boxes["ollama"].state()
        assert "disabled" in panel.boxes["voice"].state()
        assert "disabled" not in panel.boxes["chat"].state()
        assert "3.14" in panel.python_note.cget("text")
        assert panel.python_row.winfo_manager() == "grid"
        assert "disabled" in panel.install_button.state()
    finally:
        root.destroy()


def test_ticking_clean_up_ticks_voice_and_install_runs_the_plan():
    root = open_tk_or_skip()
    ran: list[list[str]] = []
    finished: list[list[str]] = []
    installed: dict[str, bool] = {}
    try:
        panel = InstallsWindow(
            root,
            schedule=lambda callback: callback(),
            probes=Probes(
                chat=lambda: installed.get("chat", False),
                voice=lambda: installed.get("voice", False),
                clips=lambda: installed.get("clips", False),
                ollama=lambda: installed.get("ollama", False),
            ),
            python_version=(3, 11),
            threaded=False,
            runner=lambda args, cwd: ran.append(list(args)) or CommandResult(0),
            pull=lambda model, progress: None,
            on_installed=finished.append,
        )
        assert panel.python_row.winfo_manager() == ""
        panel.checks["clips"].set(True)
        panel._toggled("clips")
        assert panel.checks["voice"].get() is True
        panel.checks["voice"].set(False)
        panel._toggled("voice")
        assert panel.checks["clips"].get() is False

        panel.checks["chat"].set(True)
        panel._toggled("chat")
        assert "disabled" not in panel.install_button.state()

        def planner(chosen, *, installed, python_version):
            assert chosen == ["chat"]
            return [
                Step("Installing chat", "pip", ("-r", "requirements-chat.txt"), "chat"),
                Step("Downloading chat models", "prefetch", ("chat",), "chat"),
            ]

        panel._planner = planner
        installed["chat"] = True
        panel.install()
        assert ran[0][-2:] == ["-r", "requirements-chat.txt"]
        assert ran[1][-2:] == ["prefetch", "chat"]
        assert finished == [["requirements-chat.txt"]]
        assert panel.states["chat"].cget("text") == INSTALLED
        log = panel.log.get("1.0", "end")
        assert "[1/2] Installing chat..." in log and "Done." in log
    finally:
        root.destroy()


def test_a_failed_install_shows_the_error_and_keeps_the_window_open():
    root = open_tk_or_skip()
    finished: list = []
    try:
        panel = InstallsWindow(
            root,
            schedule=lambda callback: callback(),
            probes=_probes(),
            python_version=(3, 11),
            threaded=False,
            runner=lambda args, cwd: CommandResult(1, "", "ERROR: disk full"),
            on_installed=finished.append,
            planner=lambda chosen, **_kw: [Step("Installing chat", "pip", ("-r", "requirements-chat.txt"), "chat")],
        )
        panel.checks["chat"].set(True)
        panel._toggled("chat")
        panel.install()
        assert panel.status.cget("text") == "Installing chat failed. ERROR: disk full"
        assert finished == []
        assert panel.window.winfo_exists()
    finally:
        root.destroy()
