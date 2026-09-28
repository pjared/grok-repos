"""Optional parts of Suit-O, whether each is installed, and how to install it.

The Installations window lists these with a checkbox each. Installing runs pip
against Suit-O's own Python, winget for Ollama, and a small prefetch so models
download now instead of the first time a feature is used. Every command runs
with its console hidden. Tests pass fake runners and probes, so nothing here
touches the network or the real Python unless a caller wants it to.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from suit_o.config import PROJECT_ROOT

OLLAMA_URL = "http://localhost:11434"
OLLAMA_WINGET_ID = "Ollama.Ollama"
CHAT_MODEL = "llama3.2"
# Chatterbox pins PyTorch and NumPy releases that have no builds for newer Python.
VOICE_MAX_PYTHON = (3, 12)
CUDA_TORCH_INDEX = "https://download.pytorch.org/whl/cu124"


@dataclass(frozen=True)
class Component:
    key: str
    label: str
    description: str
    size: str
    requirements: str = ""
    needs: tuple[str, ...] = ()
    needs_supported_python: bool = False


COMPONENTS: tuple[Component, ...] = (
    Component(
        key="ollama",
        label="Chat brain (Ollama + llama3.2)",
        description="The local model Suit-O uses to answer on the Chat tab.",
        size="about 3 GB",
    ),
    Component(
        key="chat",
        label="Push-to-talk (speech to text)",
        description="Hold F8 and talk to Suit-O instead of typing.",
        size="about 200 MB",
        requirements="requirements-chat.txt",
    ),
    Component(
        key="voice",
        label="Voice training (cloned voice)",
        description="Record or upload a voice and have Suit-O speak with it.",
        size="about 6 GB",
        requirements="requirements-voice.txt",
        needs_supported_python=True,
    ),
    Component(
        key="clips",
        label="Recording clean-up (Clips)",
        description="Remove music and noise, and keep one speaker, before training.",
        size="about 2 GB more",
        requirements="requirements-clips.txt",
        needs=("voice",),
        needs_supported_python=True,
    ),
)

BY_KEY = {component.key: component for component in COMPONENTS}


class InstallError(RuntimeError):
    """A step failed. The message is safe to show."""


@dataclass
class CommandResult:
    code: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[list[str], Path], CommandResult]
Progress = Callable[[str], None]


@dataclass
class Probes:
    """How to tell what is installed. Tests replace these."""

    chat: Callable[[], bool] = field(default=lambda: _findable("faster_whisper", "sounddevice"))
    voice: Callable[[], bool] = field(default=lambda: _findable("torch", "chatterbox", "sounddevice"))
    clips: Callable[[], bool] = field(default=lambda: _findable("demucs", "pyannote.audio"))
    ollama: Callable[[], bool] = field(default=lambda: ollama_ready(CHAT_MODEL))

    def installed(self, key: str) -> bool:
        check = getattr(self, key)
        try:
            return bool(check())
        except Exception:
            return False

    def missing(self) -> list[str]:
        """Parts that are not installed yet, in window order."""

        return [component.key for component in COMPONENTS if not self.installed(component.key)]


def python_supports_voice(version: tuple[int, int] | None = None) -> bool:
    major, minor = version or (sys.version_info.major, sys.version_info.minor)
    return (major, minor) <= VOICE_MAX_PYTHON


def python_label(version: tuple[int, int] | None = None) -> str:
    major, minor = version or (sys.version_info.major, sys.version_info.minor)
    return f"{major}.{minor}"


def expand(selected: Iterable[str]) -> list[str]:
    """Add what each choice depends on, in the order the window lists them."""

    wanted = set()
    for key in selected:
        if key not in BY_KEY:
            raise InstallError(f"Unknown installation: {key}")
        wanted.add(key)
        wanted.update(BY_KEY[key].needs)
    return [component.key for component in COMPONENTS if component.key in wanted]


@dataclass(frozen=True)
class Step:
    label: str
    kind: str
    args: tuple[str, ...] = ()
    component: str = ""


def plan(
    selected: Iterable[str],
    *,
    installed: Callable[[str], bool],
    python_version: tuple[int, int] | None = None,
    has_nvidia: bool | None = None,
    ollama_present: bool | None = None,
) -> list[Step]:
    """Steps for the chosen parts. Parts already installed are skipped."""

    keys = [key for key in expand(selected) if not installed(key)]
    blocked = [
        BY_KEY[key].label
        for key in keys
        if BY_KEY[key].needs_supported_python and not python_supports_voice(python_version)
    ]
    if blocked:
        raise InstallError(
            f"{', '.join(blocked)} needs Suit-O on Python 3.11. It is on Python "
            f"{python_label(python_version)}. Click Move to Python 3.11 first."
        )
    nvidia = _has_nvidia() if has_nvidia is None else has_nvidia
    steps: list[Step] = []
    for key in keys:
        component = BY_KEY[key]
        if key == "ollama":
            present = ollama_installed() if ollama_present is None else ollama_present
            if not present:
                steps.append(Step("Installing Ollama", "winget", (OLLAMA_WINGET_ID,), key))
            steps.append(Step(f"Downloading {CHAT_MODEL}", "ollama_pull", (CHAT_MODEL,), key))
            continue
        if key == "voice" and nvidia:
            steps.append(
                Step(
                    "Installing PyTorch for NVIDIA",
                    "pip",
                    ("torch", "torchaudio", "--index-url", CUDA_TORCH_INDEX),
                    key,
                )
            )
        steps.append(
            Step(f"Installing {component.label}", "pip", ("-r", component.requirements), key)
        )
        steps.append(Step(f"Downloading models for {component.label}", "prefetch", (key,), key))
    return steps


def run_plan(
    steps: list[Step],
    *,
    runner: Runner | None = None,
    progress: Progress = lambda _message: None,
    pull: Callable[[str, Progress], None] | None = None,
    wait_for_ollama: Callable[[], bool] | None = None,
    python: str | None = None,
    project: Path = PROJECT_ROOT,
    cancelled: Callable[[], bool] = lambda: False,
) -> list[str]:
    """Run the steps in order. Returns the requirement files that installed.

    Stops at the first failure with an ``InstallError``.
    """

    run = runner or hidden_runner
    exe = python or sys.executable
    installed_files: list[str] = []
    total = len(steps)
    for number, step in enumerate(steps, start=1):
        if cancelled():
            raise InstallError("Stopped.")
        progress(f"[{number}/{total}] {step.label}...")
        if step.kind == "pip":
            result = run([exe, "-m", "pip", "install", *step.args], project)
            _check(result, step)
            if step.args[:1] == ("-r",):
                installed_files.append(step.args[1])
        elif step.kind == "prefetch":
            result = run([exe, "-m", "suit_o.installs", "prefetch", step.args[0]], project)
            _check(result, step)
        elif step.kind == "winget":
            result = run(
                [
                    "winget",
                    "install",
                    "--id",
                    step.args[0],
                    "-e",
                    "--silent",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                project,
            )
            _check(result, step, hint="winget is part of Windows App Installer from the Microsoft Store.")
            waiter = wait_for_ollama or _wait_for_ollama
            if not waiter():
                raise InstallError(
                    "Ollama installed, but it is not answering yet. Start Ollama from the "
                    "Start menu, then click Install selected again."
                )
        elif step.kind == "ollama_pull":
            (pull or pull_ollama_model)(step.args[0], progress)
        else:
            raise InstallError(f"Unknown step: {step.kind}")
    progress("Done.")
    return installed_files


def _check(result: CommandResult, step: Step, *, hint: str = "") -> None:
    if result.code == 0:
        return
    detail = (result.stderr or result.stdout).strip().splitlines()
    tail = detail[-1] if detail else "the command failed"
    message = f"{step.label} failed. {tail}"
    if hint:
        message = f"{message} {hint}"
    raise InstallError(message)


def hidden_runner(args: list[str], cwd: Path) -> CommandResult:
    """Run one command with its console hidden. Not used by tests."""

    import subprocess

    from suit_o.procs import hidden_window_kwargs

    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **hidden_window_kwargs(),
        )
    except FileNotFoundError as exc:
        return CommandResult(127, "", f"{args[0]} was not found. {exc}")
    return CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")


def ollama_installed() -> bool:
    if shutil.which("ollama"):
        return True
    local = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    return local.is_file()


def ollama_ready(model: str, *, home: Path | None = None) -> bool:
    """Ollama is installed and has ``model``, even when its server is not running."""

    if ollama_has_model(model):
        return True
    if not ollama_installed():
        return False
    return ollama_model_on_disk(model, home=home)


def ollama_model_on_disk(model: str, *, home: Path | None = None) -> bool:
    name, _, tag = model.partition(":")
    root = (home or Path.home()) / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library"
    return (root / name / (tag or "latest")).is_file()


def ollama_has_model(model: str, *, fetch: Callable[[str], bytes] | None = None) -> bool:
    """True when the local Ollama server answers and already has ``model``."""

    getter = fetch or _http_get
    try:
        raw = getter(f"{OLLAMA_URL}/api/tags")
    except OSError:
        return False
    try:
        models = json.loads(raw.decode("utf-8")).get("models") or []
    except (ValueError, AttributeError):
        return False
    names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
    return model in names or f"{model}:latest" in names


def pull_ollama_model(
    model: str,
    progress: Progress,
    *,
    stream: Callable[[str, dict], Iterator[str]] | None = None,
) -> None:
    """Download ``model`` through the local Ollama server, reporting percent."""

    lines = (stream or _http_post_lines)(f"{OLLAMA_URL}/api/pull", {"model": model})
    last = -5
    try:
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("error"):
                raise InstallError(f"Downloading {model} failed. {row['error']}")
            total = row.get("total") or 0
            done = row.get("completed") or 0
            if total:
                percent = int(100 * done / total)
                if percent >= last + 5:
                    last = percent
                    progress(f"Downloading {model}: {percent}%")
            if row.get("status") == "success":
                return
    except OSError as exc:
        raise InstallError(f"Could not reach Ollama at {OLLAMA_URL}. {exc}") from exc
    raise InstallError(f"Downloading {model} did not finish.")


def prefetch(key: str) -> None:
    """Download a part's models now. Runs in a separate Python, after pip."""

    if key == "chat":
        from faster_whisper import download_model

        download_model("base")
        return
    if key == "voice":
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device="cpu")
        del model
        return
    if key == "clips":
        from demucs.pretrained import get_model

        get_model("htdemucs")
        return
    raise InstallError(f"Nothing to download for {key}")


def _wait_for_ollama(seconds: float = 60.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            _http_get(f"{OLLAMA_URL}/api/version")
            return True
        except OSError:
            time.sleep(2)
    return False


def _has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None


def _findable(*modules: str) -> bool:
    """True when every module is installed. Looks it up without importing it,
    so checking for PyTorch does not load PyTorch into the window."""

    import importlib.util

    for name in modules:
        try:
            if importlib.util.find_spec(name) is None:
                return False
        except (ImportError, ValueError):
            return False
    return True


def _http_get(url: str) -> bytes:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise OSError(str(exc.reason)) from exc


def _http_post_lines(url: str, payload: dict) -> Iterator[str]:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=600)
    except urllib.error.URLError as exc:
        raise OSError(str(exc.reason)) from exc
    with response:
        for raw in response:
            yield raw.decode("utf-8", errors="replace")
