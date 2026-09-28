"""The Installations checklist: plans, dependencies, and running steps. No network."""

from __future__ import annotations

import json
from pathlib import Path

from suit_o.installs.__main__ import main as installs_main
from suit_o.installs.components import (
    BY_KEY,
    CHAT_MODEL,
    COMPONENTS,
    CUDA_TORCH_INDEX,
    CommandResult,
    InstallError,
    Probes,
    Step,
    expand,
    ollama_has_model,
    ollama_model_on_disk,
    plan,
    pull_ollama_model,
    python_supports_voice,
    run_plan,
)

NOTHING = lambda _key: False  # noqa: E731


def test_every_part_has_a_label_size_and_known_requirements():
    root = Path(__file__).resolve().parent.parent
    assert [c.key for c in COMPONENTS] == ["ollama", "chat", "voice", "clips"]
    for component in COMPONENTS:
        assert component.label and component.description and component.size
        if component.requirements:
            assert (root / component.requirements).is_file()


def test_clean_up_brings_voice_along_and_order_is_stable():
    assert expand(["clips"]) == ["voice", "clips"]
    assert expand(["clips", "ollama"]) == ["ollama", "voice", "clips"]
    try:
        expand(["mystery"])
    except InstallError as exc:
        assert "mystery" in str(exc)
    else:
        raise AssertionError("an unknown part was accepted")


def test_voice_needs_python_311_and_says_how_to_fix_it():
    assert python_supports_voice((3, 11)) is True
    assert python_supports_voice((3, 12)) is True
    assert python_supports_voice((3, 14)) is False
    try:
        plan(["voice"], installed=NOTHING, python_version=(3, 14), has_nvidia=False)
    except InstallError as exc:
        assert "3.11" in str(exc) and "3.14" in str(exc)
        assert "Move to Python 3.11" in str(exc)
    else:
        raise AssertionError("voice was planned on Python 3.14")
    chat_only = plan(["chat"], installed=NOTHING, python_version=(3, 14), has_nvidia=False)
    assert [step.kind for step in chat_only] == ["pip", "prefetch"]


def test_plan_skips_installed_parts_and_adds_cuda_torch_only_for_nvidia():
    installed = {"chat"}
    steps = plan(
        ["chat", "voice", "ollama"],
        installed=lambda key: key in installed,
        python_version=(3, 11),
        has_nvidia=True,
        ollama_present=False,
    )
    assert [(step.kind, step.component) for step in steps] == [
        ("winget", "ollama"),
        ("ollama_pull", "ollama"),
        ("pip", "voice"),
        ("pip", "voice"),
        ("prefetch", "voice"),
    ]
    assert CUDA_TORCH_INDEX in steps[2].args
    assert steps[3].args == ("-r", "requirements-voice.txt")

    amd = plan(["voice"], installed=NOTHING, python_version=(3, 11), has_nvidia=False)
    assert all(CUDA_TORCH_INDEX not in step.args for step in amd)
    ollama_ready = plan(["ollama"], installed=NOTHING, python_version=(3, 11), ollama_present=True)
    assert [step.kind for step in ollama_ready] == ["ollama_pull"]


def test_run_plan_runs_hidden_commands_in_order_and_reports_installed_files(tmp_path: Path):
    seen: list[list[str]] = []
    messages: list[str] = []
    pulled: list[str] = []

    def runner(args, cwd):
        seen.append(list(args))
        assert cwd == tmp_path
        return CommandResult(0)

    steps = [
        Step("Installing Ollama", "winget", ("Ollama.Ollama",), "ollama"),
        Step("Downloading llama3.2", "ollama_pull", (CHAT_MODEL,), "ollama"),
        Step("Installing chat", "pip", ("-r", "requirements-chat.txt"), "chat"),
        Step("Downloading chat models", "prefetch", ("chat",), "chat"),
    ]
    files = run_plan(
        steps,
        runner=runner,
        progress=messages.append,
        pull=lambda model, _progress: pulled.append(model),
        wait_for_ollama=lambda: True,
        python="py",
        project=tmp_path,
    )
    assert files == ["requirements-chat.txt"]
    assert seen[0][:4] == ["winget", "install", "--id", "Ollama.Ollama"]
    assert "--silent" in seen[0]
    assert seen[1] == ["py", "-m", "pip", "install", "-r", "requirements-chat.txt"]
    assert seen[2] == ["py", "-m", "suit_o.installs", "prefetch", "chat"]
    assert pulled == [CHAT_MODEL]
    assert messages[0] == "[1/4] Installing Ollama..."
    assert messages[-1] == "Done."


def test_run_plan_stops_at_the_first_failure_with_the_last_error_line(tmp_path: Path):
    calls: list[list[str]] = []

    def runner(args, cwd):
        calls.append(args)
        return CommandResult(1, "", "Collecting torch\nERROR: No matching distribution found for torch")

    steps = [
        Step("Installing voice", "pip", ("-r", "requirements-voice.txt"), "voice"),
        Step("Downloading voice models", "prefetch", ("voice",), "voice"),
    ]
    try:
        run_plan(steps, runner=runner, python="py", project=tmp_path)
    except InstallError as exc:
        assert str(exc) == "Installing voice failed. ERROR: No matching distribution found for torch"
    else:
        raise AssertionError("a failed pip install was accepted")
    assert len(calls) == 1

    try:
        run_plan(steps, runner=runner, python="py", project=tmp_path, cancelled=lambda: True)
    except InstallError as exc:
        assert str(exc) == "Stopped."
    else:
        raise AssertionError("a cancelled install kept going")


def test_ollama_checks_the_model_and_pull_reports_percent():
    body = json.dumps({"models": [{"name": "llama3.2:latest"}]}).encode()
    assert ollama_has_model("llama3.2", fetch=lambda _url: body) is True
    assert ollama_has_model("mistral", fetch=lambda _url: body) is False

    def down(_url):
        raise OSError("refused")

    assert ollama_has_model("llama3.2", fetch=down) is False

    rows = [
        {"status": "pulling", "total": 100, "completed": 0},
        {"status": "pulling", "total": 100, "completed": 2},
        {"status": "pulling", "total": 100, "completed": 50},
        {"status": "pulling", "total": 100, "completed": 100},
        {"status": "success"},
    ]
    messages: list[str] = []
    pull_ollama_model(
        "llama3.2",
        messages.append,
        stream=lambda _url, _payload: iter(json.dumps(row) + "\n" for row in rows),
    )
    assert messages == ["Downloading llama3.2: 0%", "Downloading llama3.2: 50%", "Downloading llama3.2: 100%"]

    try:
        pull_ollama_model(
            "llama3.2",
            messages.append,
            stream=lambda _url, _payload: iter([json.dumps({"error": "disk full"})]),
        )
    except InstallError as exc:
        assert "disk full" in str(exc)
    else:
        raise AssertionError("a pull error was accepted")


def test_probes_list_what_is_missing_and_survive_a_broken_check():
    def broken():
        raise RuntimeError("boom")

    probes = Probes(chat=lambda: True, voice=broken, clips=lambda: False, ollama=lambda: True)
    assert probes.missing() == ["voice", "clips"]
    everything = Probes(chat=lambda: True, voice=lambda: True, clips=lambda: True, ollama=lambda: True)
    assert everything.missing() == []


def test_prefetch_entry_point_rejects_bad_arguments(capsys):
    assert installs_main([]) == 2
    assert installs_main(["prefetch", "nothing"]) == 1
    assert "nothing" in capsys.readouterr().err
    assert BY_KEY["clips"].needs == ("voice",)


def test_a_downloaded_model_counts_even_when_ollama_is_not_running(tmp_path: Path):
    assert ollama_model_on_disk("llama3.2", home=tmp_path) is False
    manifest = tmp_path / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "llama3.2" / "latest"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    assert ollama_model_on_disk("llama3.2", home=tmp_path) is True
    assert ollama_model_on_disk("llama3.2:3b", home=tmp_path) is False
