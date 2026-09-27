"""Hot reload, the local settings overlay, and the Update command."""

from __future__ import annotations

import os
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from suit_o.local_config import local_config_path, migrate_user_settings, store_personal_settings
from suit_o.models import EventType
from suit_o.gsi.payloads import make_payload
from suit_o.reload import (
    ChangeDebouncer,
    FileWatcher,
    RestartState,
    choose_reload,
    consume_restart_state,
    gui_restart_argv,
    restart_is_blocked,
    write_restart_state,
)
from suit_o.speech.stub import StubSpeechBackend
from suit_o.update import (
    CommandResult,
    explain_git_failure,
    install_requirements,
    interpret_check_runs,
    requirement_paths,
    run_git_update,
)

JBL_CHAT = "Headset Earphone (JBL Quantum 950X Wireless For Xbox Chat)"


def test_debouncer_waits_for_a_quiet_gap_then_fires_once():
    debouncer = ChangeDebouncer(0.5)
    assert debouncer.ready(0.0) is None
    debouncer.note("content", 1.0)
    debouncer.note("code", 1.2)
    debouncer.note("code", 1.4)
    assert debouncer.ready(1.8) is None
    assert debouncer.ready(1.9) == ["code", "content"]
    assert debouncer.ready(3.0) is None
    assert choose_reload(["code", "content"]) == "restart"
    assert choose_reload(["content"]) == "reload"


def test_watcher_collapses_a_multi_file_burst_and_ignores_our_own_write(tmp_path: Path):
    root = tmp_path
    (root / "suit_o").mkdir()
    (root / "lines").mkdir()
    config_path = root / "config.yaml"
    config_path.write_text("server: {}\n", encoding="utf-8")
    lines_path = root / "lines" / "lines.yaml"
    lines_path.write_text("events: {}\n", encoding="utf-8")
    watcher = FileWatcher(root, config_path=config_path, lines_path=lines_path, delay=0.5)
    assert watcher.scan(0.0) is None

    (root / "suit_o" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "suit_o" / "b.py").write_text("y = 2\n", encoding="utf-8")
    assert watcher.scan(1.0) is None
    assert watcher.scan(1.5) == ["code"]
    assert watcher.scan(2.0) is None

    local = local_config_path(config_path)
    local.write_text("mute: true\n", encoding="utf-8")
    watcher.ignore(local, until=5.0)
    assert watcher.scan(1.0) is None
    assert watcher.scan(6.0) is None
    os.utime(local, ns=(7_000_000_000, 7_000_000_000))
    assert watcher.scan(7.0) is None
    assert choose_reload(watcher.scan(7.5) or []) == "reload"


def test_local_overlay_wins_and_migration_keeps_the_jbl_device(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    original = path.read_bytes()
    assert migrate_user_settings(path) is False
    assert path.read_bytes() == original
    assert not local_config_path(path).exists()
    assert load_config(path).updates.check_on_launch is False

    layered = local_config_path(path)
    layered.write_text("speech:\n  volume: 0.33\n", encoding="utf-8")
    assert load_config(path).speech.volume == 0.33
    assert "volume: 0.85" in path.read_text(encoding="utf-8")
    layered.unlink()

    edited = path.read_text(encoding="utf-8").replace(
        'output_device: ""',
        f'output_device: "{JBL_CHAT}"',
        1,
    )
    path.write_text(edited, encoding="utf-8")
    assert migrate_user_settings(path) is True
    saved = load_config(path)
    assert saved.speech.output_device == JBL_CHAT
    restored = path.read_text(encoding="utf-8")
    assert 'output_device: ""' in restored
    assert JBL_CHAT not in restored
    assert "virtual cable" in restored
    assert "Do not set a microphone" in restored
    local_text = local_config_path(path).read_text(encoding="utf-8")
    assert JBL_CHAT in local_text

    local_config_path(path).write_text("speech:\n  volume: 0.2\n", encoding="utf-8")
    before = path.read_bytes()
    assert migrate_user_settings(path) is False
    assert path.read_bytes() == before
    assert local_config_path(path).read_text(encoding="utf-8").strip().endswith("volume: 0.2")


def test_app_save_writes_the_local_file_and_leaves_config_yaml(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    original = path.read_bytes()
    config = load_config(DEFAULT_CONFIG_PATH)
    app = SuitOApp(
        config,
        backend=StubSpeechBackend(),
        config_path=path,
        output_devices=lambda: [JBL_CHAT],
    )
    app.set_volume(0.33)
    app.set_output_device(JBL_CHAT)
    app.set_muted(True)
    app.save_preferences()
    assert path.read_bytes() == original
    saved = load_config(path)
    assert saved.speech.volume == 0.33
    assert saved.speech.output_device == JBL_CHAT
    assert saved.mute is True
    assert "virtual cable" in path.read_text(encoding="utf-8")


def test_invalid_config_and_lines_keep_the_previous_settings(tmp_path: Path):
    lines = tmp_path / "lines.yaml"
    lines.write_text("events:\n  kill:\n    - Hello from the stock file.\n", encoding="utf-8")
    path = tmp_path / "config.yaml"
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    text = text.replace("port: 3000", "port: 0")
    text = text.replace("lines/lines.yaml", lines.as_posix())
    path.write_text(text, encoding="utf-8")
    app = SuitOApp(load_config(path), backend=StubSpeechBackend(), config_path=path)
    assert app.config.speech.volume == 0.85

    local_config_path(path).write_text("speech: [\n", encoding="utf-8")
    rejected = app.reload_content()
    assert rejected.ok is False
    assert rejected.applied is False
    assert "Kept the previous settings" in rejected.message
    assert app.config.speech.volume == 0.85
    assert any("Kept the previous settings" in item.message for item in app.activity())

    local_config_path(path).write_text("speech:\n  volume: 0.4\n", encoding="utf-8")
    applied = app.reload_content()
    assert applied.ok is True
    assert applied.applied is True
    assert app.config.speech.volume == 0.4

    lines.write_text("not: events\n", encoding="utf-8")
    kept = app.reload_content()
    assert kept.ok is False
    assert "Kept the previous lines" in kept.message
    assert app.config.speech.volume == 0.4
    assert app.lines.lines_for(EventType.KILL) == ["Hello from the stock file."]

    broken = path.read_text(encoding="utf-8").replace("suito-local-change-me", "suito-local-changed")
    path.write_text(broken, encoding="utf-8")
    restart = app.reload_content()
    assert restart.restart is True
    assert app.config.server.token == "suito-local-change-me"
    assert app.config.speech.volume == 0.4


def test_restart_state_round_trip_and_launch_argv(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("server: {}\n", encoding="utf-8")
    write_restart_state(path, RestartState(12, -4, 800, 600, 2, "Reloaded", "0.17.0"))
    state = consume_restart_state(path)
    assert state is not None
    assert (state.x, state.y, state.width, state.height, state.tab, state.notice) == (
        12,
        -4,
        800,
        600,
        2,
        "Reloaded",
    )
    assert state.previous_version == "0.17.0"
    assert consume_restart_state(path) is None
    argv = gui_restart_argv(path)
    assert argv[1:4] == ["-m", "suit_o.gui", "--config"]
    assert argv[-1] == str(path)


def test_update_reports_local_changes_fast_forward_and_requirements(tmp_path: Path):
    project = tmp_path / "suit-o-cs2"
    project.mkdir()
    repo = tmp_path
    (repo / ".git").mkdir()
    (project / "requirements.txt").write_text("pyyaml\n", encoding="utf-8")
    (project / "requirements-voice.txt").write_text("torch\n", encoding="utf-8")

    def blocked(_args, _cwd):
        return CommandResult(
            1,
            "",
            "error: Your local changes to the following files would be overwritten by merge:\n"
            "\tconfig.yaml\n"
            "Please commit your changes or stash them before you merge.\n"
            "Aborting\n",
        )

    def blocked_pull(args, cwd):
        if args[:2] == ["git", "rev-parse"]:
            return CommandResult(0, "abc\n", "")
        return blocked(args, cwd)

    refused = run_git_update(project, blocked_pull)
    assert refused.ok is False
    assert refused.changed is False
    assert "config.yaml" in refused.message
    assert "config.local.yaml" in refused.message
    assert "git pull" not in refused.message

    diverged = run_git_update(
        project,
        lambda args, _cwd: CommandResult(0, "abc\n", "")
        if args[:2] == ["git", "rev-parse"]
        else CommandResult(1, "", "fatal: Not possible to fast-forward, aborting.\n"),
    )
    assert "fast-forward" not in diverged.message
    assert "will not merge" in diverged.message

    def current(args, _cwd):
        if args[:2] == ["git", "rev-parse"]:
            return CommandResult(0, "abc\n", "")
        return CommandResult(0, "Already up to date.\n", "")

    same = run_git_update(project, current)
    assert same.ok is True
    assert same.changed is False
    assert same.message == "Already up to date."

    heads = iter(["aaa\n", "bbb\n"])

    def pulled(args, _cwd):
        if args[:2] == ["git", "rev-parse"]:
            return CommandResult(0, next(heads), "")
        if args[:2] == ["git", "diff"]:
            return CommandResult(
                0,
                "suit-o-cs2/requirements.txt\nsuit-o-cs2/suit_o/app.py\n",
                "",
            )
        return CommandResult(0, "Updating aaa..bbb\n", "")

    updated = run_git_update(project, pulled)
    assert updated.ok is True
    assert updated.changed is True
    assert updated.requirements == (str((project / "requirements.txt").resolve()),)
    assert "requirements.txt" in updated.message
    assert "requirements-voice.txt" not in updated.message

    pip_error = install_requirements(
        updated.requirements,
        lambda args, _cwd: CommandResult(1, "", "No matching distribution\n"),
    )
    assert pip_error is not None
    assert pip_error.startswith("Could not install requirements.txt.")
    assert requirement_paths(
        ["other/requirements.txt"],
        repo=repo,
        project=project,
    ) == []


def test_check_runs_ignore_other_workflows_and_wait_for_pytest():
    assert interpret_check_runs({}) == "pending"
    assert interpret_check_runs({"check_runs": []}) == "pending"
    assert interpret_check_runs("nope") == "pending"
    other = {"name": "lint", "status": "completed", "conclusion": "failure"}
    assert interpret_check_runs({"check_runs": [other]}) == "pending"
    pending = {"name": "pytest", "status": "in_progress", "conclusion": None}
    assert interpret_check_runs({"check_runs": [pending]}) == "pending"
    failed = {"name": "pytest", "status": "completed", "conclusion": "failure"}
    assert interpret_check_runs({"check_runs": [failed, other]}) == "failure"
    cancelled = {"name": "Suit-O tests / pytest", "status": "completed", "conclusion": "cancelled"}
    assert interpret_check_runs({"check_runs": [cancelled]}) == "failure"
    skipped = {"name": "pytest", "status": "completed", "conclusion": "skipped"}
    passed = {"name": "suit-o", "status": "completed", "conclusion": "success"}
    assert interpret_check_runs({"check_runs": [skipped, passed]}) == "success"
    assert interpret_check_runs({"check_runs": [passed]}) == "success"


def _remote_runner(heads: list[str], pulls: list[list[str]]):
    sequence = iter(heads)

    def runner(args, _cwd):
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, next(sequence), "")
        if args == ["git", "fetch", "origin"]:
            return CommandResult(0, "", "")
        if args == ["git", "rev-parse", "origin/main"]:
            return CommandResult(0, "bbb\n", "")
        if args[:2] == ["git", "pull"]:
            pulls.append(args)
            return CommandResult(0, "Updating aaa..bbb\n", "")
        if args[:2] == ["git", "diff"]:
            return CommandResult(0, "", "")
        return CommandResult(1, "", f"unexpected {' '.join(args)}")

    return runner


def test_update_refuses_a_commit_until_its_tests_pass(tmp_path: Path):
    project = tmp_path / "suit-o-cs2"
    project.mkdir()
    (tmp_path / ".git").mkdir()
    pulls: list[list[str]] = []

    pending = run_git_update(
        project,
        _remote_runner(["aaa\n"], pulls),
        check=lambda sha: "pending",
    )
    assert pending.ok is False
    assert pending.changed is False
    assert "bbb"[:7] in pending.message
    assert "still running" in pending.message
    assert pulls == []

    failed = run_git_update(
        project,
        _remote_runner(["aaa\n"], pulls),
        check=lambda sha: "failure",
    )
    assert failed.ok is False
    assert "Tests failed" in failed.message
    assert "bbb"[:7] in failed.message
    assert pulls == []

    seen: list[str] = []
    updated = run_git_update(
        project,
        _remote_runner(["aaa\n", "aaa\n", "bbb\n"], pulls),
        check=lambda sha: seen.append(sha) or "success",
    )
    assert updated.ok is True
    assert updated.changed is True
    assert pulls and pulls[-1][:2] == ["git", "pull"]
    assert seen == ["bbb"]


def test_restart_waits_for_the_menu_or_the_end_of_the_round(tmp_path: Path):
    assert restart_is_blocked(None, None) is False
    assert restart_is_blocked("menu", "live") is False
    assert restart_is_blocked("playing", "live") is True
    assert restart_is_blocked("playing", "freezetime") is False
    assert restart_is_blocked("playing", "over") is False
    assert restart_is_blocked("textinput", "live") is True

    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    app = SuitOApp(load_config(DEFAULT_CONFIG_PATH), backend=StubSpeechBackend(), config_path=path)
    assert app.restart_blocked() is False
    app._handle(make_payload(activity="playing", round_phase="live"))
    assert app.restart_blocked() is True
    app._handle(make_payload(activity="playing", round_phase="freezetime"))
    assert app.restart_blocked() is False
    app._handle(make_payload(activity="textinput", round_phase="live"))
    assert app.restart_blocked() is True
    app._handle(make_payload(activity="menu", round_phase="live"))
    assert app.restart_blocked() is False


def test_store_refuses_a_microphone_without_writing_local(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    try:
        store_personal_settings(path, output_device="Headset Microphone (JBL)")
        refused = False
    except ConfigError:
        refused = True
    assert refused
    assert not local_config_path(path).exists()


def test_explain_git_failure_is_a_plain_sentence():
    message = explain_git_failure("fatal: Not possible to fast-forward, aborting.")
    assert message == (
        "Update stopped because this copy has commits that are not on the remote. "
        "Suit-O will not merge or rebase. Update this copy by hand."
    )
