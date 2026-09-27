"""Hot reload, the local settings overlay, and the Update command."""

from __future__ import annotations

import os
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from suit_o.local_config import (
    local_config_path,
    migrate_user_settings,
    read_installed_requirements,
    remember_installed_requirements,
    store_personal_settings,
)
from suit_o.models import EventType
from suit_o.gsi.payloads import make_payload
from suit_o.reload import (
    ChangeDebouncer,
    FileWatcher,
    RestartState,
    change_kind,
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
    interpret_workflow_runs,
    requirement_paths,
    run_git_update,
)

CHAT = "Headset Earphone (Example Chat)"


def test_watcher_ignores_renders_clips_recordings_and_lineup_data(tmp_path: Path):
    root = tmp_path
    (root / "voices" / "hero" / "cache").mkdir(parents=True)
    (root / "voices" / "hero" / "clips").mkdir()
    (root / "voices" / "_session").mkdir()
    (root / "lineup-data").mkdir()
    config_path = root / "config.yaml"
    config_path.write_text("server: {}\n", encoding="utf-8")
    kwargs = {"root": root, "config_path": config_path, "lines_path": None}
    assert change_kind(root / "voices" / "hero" / "cache" / "line.wav", **kwargs) is None
    assert change_kind(root / "voices" / "hero" / "clips" / "take.wav", **kwargs) is None
    assert change_kind(root / "voices" / "_session" / "take.wav", **kwargs) is None
    assert change_kind(root / "voices" / "session" / "take.wav", **kwargs) is None
    assert change_kind(root / "lineup-data" / "pack.png", **kwargs) is None
    profile = root / "voices" / "hero" / "profile.yaml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    assert change_kind(profile, **kwargs) == "content"

    watcher = FileWatcher(root, config_path=config_path, lines_path=None, delay=0.5)
    assert watcher.scan(0.0) is None
    (root / "voices" / "hero" / "cache" / "line.wav").write_bytes(b"RIFF")
    (root / "voices" / "hero" / "clips" / "take.wav").write_bytes(b"RIFF")
    (root / "voices" / "_session" / "take.wav").write_bytes(b"RIFF")
    assert watcher.scan(1.0) is None
    assert watcher.scan(1.6) is None
    profile.write_text("name: Hero\n", encoding="utf-8")
    assert watcher.scan(2.0) is None
    assert watcher.scan(2.6) == ["content"]


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
        f'output_device: "{CHAT}"',
        1,
    )
    path.write_text(edited, encoding="utf-8")
    assert migrate_user_settings(path) is True
    saved = load_config(path)
    assert saved.speech.output_device == CHAT
    restored = path.read_text(encoding="utf-8")
    assert 'output_device: ""' in restored
    assert CHAT not in restored
    assert "virtual cable" in restored
    assert "Do not set a microphone" in restored
    local_text = local_config_path(path).read_text(encoding="utf-8")
    assert CHAT in local_text

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
        output_devices=lambda: [CHAT],
    )
    app.set_volume(0.33)
    app.set_output_device(CHAT)
    app.set_muted(True)
    app.save_preferences()
    assert path.read_bytes() == original
    saved = load_config(path)
    assert saved.speech.volume == 0.33
    assert saved.speech.output_device == CHAT
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
    assert state.greeted is False
    assert consume_restart_state(path) is None
    write_restart_state(path, RestartState(1, 2, 3, 4, 0, "Reloaded", "", True))
    carried = consume_restart_state(path)
    assert carried is not None
    assert carried.greeted is True
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

    def blocked(args, _cwd):
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, "aaa\n", "")
        if args == ["git", "fetch", "origin"]:
            return CommandResult(0, "", "")
        if args == ["git", "rev-parse", "origin/main"]:
            return CommandResult(0, "bbb\n", "")
        if args == ["git", "merge", "--ff-only", "bbb"]:
            return CommandResult(
                1,
                "",
                "error: Your local changes to the following files would be overwritten by merge:\n"
                "\tconfig.yaml\n"
                "Please commit your changes or stash them before you merge.\n"
                "Aborting\n",
            )
        return CommandResult(1, "", f"unexpected {args}")

    refused = run_git_update(project, blocked, check=lambda _sha: "success")
    assert refused.ok is False
    assert refused.changed is False
    assert "config.yaml" in refused.message
    assert "config.local.yaml" in refused.message
    assert "git pull" not in refused.message

    def diverged_runner(args, _cwd):
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, "aaa\n", "")
        if args == ["git", "fetch", "origin"]:
            return CommandResult(0, "", "")
        if args == ["git", "rev-parse", "origin/main"]:
            return CommandResult(0, "bbb\n", "")
        if args[:3] == ["git", "merge", "--ff-only"]:
            return CommandResult(1, "", "fatal: Not possible to fast-forward, aborting.\n")
        return CommandResult(1, "", f"unexpected {args}")

    diverged = run_git_update(project, diverged_runner, check=lambda _sha: "success")
    assert "fast-forward" not in diverged.message
    assert "will not merge" in diverged.message

    def current(args, _cwd):
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, "abc\n", "")
        if args == ["git", "fetch", "origin"]:
            return CommandResult(0, "", "")
        if args == ["git", "rev-parse", "origin/main"]:
            return CommandResult(0, "abc\n", "")
        return CommandResult(1, "", f"unexpected {args}")

    same = run_git_update(project, current, check=lambda _sha: "success")
    assert same.ok is True
    assert same.changed is False
    assert same.message == "Already up to date."

    heads = iter(["aaa\n", "bbb\n"])

    def pulled(args, _cwd):
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, next(heads), "")
        if args == ["git", "fetch", "origin"]:
            return CommandResult(0, "", "")
        if args == ["git", "rev-parse", "origin/main"]:
            return CommandResult(0, "bbb\n", "")
        if args == ["git", "merge", "--ff-only", "bbb"]:
            return CommandResult(0, "Updating aaa..bbb\n", "")
        if args[:2] == ["git", "diff"]:
            return CommandResult(
                0,
                "suit-o-cs2/requirements.txt\nsuit-o-cs2/suit_o/app.py\n",
                "",
            )
        return CommandResult(1, "", f"unexpected {args}")

    updated = run_git_update(project, pulled, check=lambda _sha: "success")
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


def test_update_skips_optional_requirements_until_they_are_installed(tmp_path: Path):
    project = tmp_path / "suit-o-cs2"
    project.mkdir()
    repo = tmp_path
    (repo / ".git").mkdir()
    (project / "requirements.txt").write_text("pyyaml\n", encoding="utf-8")
    (project / "requirements-voice.txt").write_text("torch\n", encoding="utf-8")
    (project / "requirements-clips.txt").write_text("demucs\n", encoding="utf-8")
    (project / "config.yaml").write_text("mute: false\n", encoding="utf-8")

    def runner(after: str):
        heads = iter(["aaa\n", after])

        def pulled(args, _cwd):
            if args == ["git", "rev-parse", "HEAD"]:
                return CommandResult(0, next(heads), "")
            if args == ["git", "fetch", "origin"]:
                return CommandResult(0, "", "")
            if args == ["git", "rev-parse", "origin/main"]:
                return CommandResult(0, after, "")
            if args == ["git", "merge", "--ff-only", after.strip()]:
                return CommandResult(0, "Updating\n", "")
            if args[:2] == ["git", "diff"]:
                return CommandResult(
                    0,
                    "suit-o-cs2/requirements.txt\n"
                    "suit-o-cs2/requirements-voice.txt\n"
                    "suit-o-cs2/requirements-clips.txt\n",
                    "",
                )
            return CommandResult(1, "", f"unexpected {args}")

        return pulled

    skipped = run_git_update(project, runner("bbb\n"), check=lambda _sha: "success")
    assert skipped.requirements == (str((project / "requirements.txt").resolve()),)
    assert "requirements-voice.txt" not in skipped.message

    remember_installed_requirements(project / "config.yaml", ["requirements-voice.txt"])
    assert read_installed_requirements(project / "config.yaml") == {"requirements-voice.txt"}
    marked = run_git_update(project, runner("ccc\n"), check=lambda _sha: "success")
    names = {Path(item).name for item in marked.requirements}
    assert names == {"requirements.txt", "requirements-voice.txt"}
    assert "requirements-clips.txt" not in names


def _workflow(sha: str, *, status: str, conclusion: str | None, updated_at: str = "2026-09-27T00:00:00Z"):
    return {
        "name": "Suit-O tests",
        "path": ".github/workflows/suit-o-tests.yml",
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
        "updated_at": updated_at,
    }


def test_workflow_runs_ignore_a_check_named_pytest():
    sha = "bbb"
    assert interpret_workflow_runs({}, sha) == "pending"
    assert interpret_workflow_runs({"workflow_runs": []}, sha) == "pending"
    assert interpret_workflow_runs("nope", sha) == "pending"
    named_pytest = {
        "name": "pytest",
        "path": ".github/workflows/other.yml",
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
    }
    assert interpret_workflow_runs({"check_runs": [named_pytest]}, sha) == "pending"
    assert interpret_workflow_runs({"workflow_runs": [named_pytest]}, sha) == "pending"
    pending = _workflow(sha, status="in_progress", conclusion=None)
    assert interpret_workflow_runs({"workflow_runs": [pending]}, sha) == "pending"
    failed = _workflow(sha, status="completed", conclusion="failure")
    assert interpret_workflow_runs({"workflow_runs": [failed]}, sha) == "failure"
    cancelled = _workflow(sha, status="completed", conclusion="cancelled")
    assert interpret_workflow_runs({"workflow_runs": [cancelled]}, sha) == "failure"
    passed = _workflow(sha, status="completed", conclusion="success")
    newer_failure = _workflow(
        sha, status="completed", conclusion="failure", updated_at="2026-09-27T01:00:00Z"
    )
    assert interpret_workflow_runs({"workflow_runs": [passed, newer_failure]}, sha) == "failure"
    assert interpret_workflow_runs({"workflow_runs": [passed]}, "ccc") == "pending"
    assert interpret_workflow_runs({"workflow_runs": [passed]}, sha) == "success"


def _remote_runner(heads: list[str], merges: list[list[str]]):
    sequence = iter(heads)

    def runner(args, _cwd):
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, next(sequence), "")
        if args == ["git", "fetch", "origin"]:
            return CommandResult(0, "", "")
        if args == ["git", "rev-parse", "origin/main"]:
            return CommandResult(0, "bbb\n", "")
        if args[:3] == ["git", "merge", "--ff-only"]:
            merges.append(args)
            return CommandResult(0, "Updating aaa..bbb\n", "")
        if args[:2] == ["git", "pull"]:
            merges.append(args)
            return CommandResult(1, "", "plain pull is not used")
        if args[:2] == ["git", "diff"]:
            return CommandResult(0, "", "")
        return CommandResult(1, "", f"unexpected {' '.join(args)}")

    return runner


def test_update_refuses_a_commit_until_its_tests_pass(tmp_path: Path):
    project = tmp_path / "suit-o-cs2"
    project.mkdir()
    (tmp_path / ".git").mkdir()
    merges: list[list[str]] = []

    pending = run_git_update(
        project,
        _remote_runner(["aaa\n"], merges),
        check=lambda sha: "pending",
    )
    assert pending.ok is False
    assert pending.changed is False
    assert "bbb"[:7] in pending.message
    assert "still running" in pending.message
    assert merges == []

    failed = run_git_update(
        project,
        _remote_runner(["aaa\n"], merges),
        check=lambda sha: "failure",
    )
    assert failed.ok is False
    assert "Tests failed" in failed.message
    assert "bbb"[:7] in failed.message
    assert merges == []

    seen: list[str] = []
    updated = run_git_update(
        project,
        _remote_runner(["aaa\n", "bbb\n"], merges),
        check=lambda sha: seen.append(sha) or "success",
    )
    assert updated.ok is True
    assert updated.changed is True
    assert merges == [["git", "merge", "--ff-only", "bbb"]]
    assert seen == ["bbb"]


def test_update_merges_the_checked_sha_when_a_newer_commit_lands(tmp_path: Path):
    """A commit that appears after the check must not be installed."""

    project = tmp_path / "suit-o-cs2"
    project.mkdir()
    (tmp_path / ".git").mkdir()
    remotes = iter(["bbb\n", "ccc\n"])
    merged: list[str] = []
    checked: list[str] = []

    def runner(args, _cwd):
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, "bbb\n" if merged else "aaa\n", "")
        if args == ["git", "fetch", "origin"]:
            return CommandResult(0, "", "")
        if args == ["git", "rev-parse", "origin/main"]:
            return CommandResult(0, next(remotes), "")
        if args[:2] == ["git", "pull"]:
            raise AssertionError("Update used git pull")
        if args[:3] == ["git", "merge", "--ff-only"]:
            merged.append(args[3])
            return CommandResult(0, "Fast-forward\n", "")
        if args[:2] == ["git", "diff"]:
            return CommandResult(0, "", "")
        return CommandResult(1, "", f"unexpected {args}")

    def check(sha: str) -> str:
        checked.append(sha)
        return "success" if sha == "bbb" else "pending"

    outcome = run_git_update(project, runner, check=check)
    assert outcome.ok is True
    assert outcome.changed is True
    assert checked == ["bbb"]
    assert merged == ["bbb"]
    assert next(remotes) == "ccc\n"


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
        store_personal_settings(path, output_device="Headset Microphone (Example)")
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
