"""Fast-forward the Suit-O checkout and reinstall requirements that changed.

The desktop window calls this. Tests pass a fake runner, so nothing here
invokes git or pip unless a caller wants the real commands.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REQUIREMENT_NAMES = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-voice.txt",
    "requirements-clips.txt",
    "requirements-chat.txt",
)
OPTIONAL_REQUIREMENTS = frozenset(
    {
        "requirements-voice.txt",
        "requirements-clips.txt",
        "requirements-chat.txt",
    }
)

GITHUB_OWNER = "pjared"
GITHUB_REPO = "grok-repos"
SUIT_O_WORKFLOW = "suit-o-tests.yml"


@dataclass(frozen=True)
class CommandResult:
    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class UpdateOutcome:
    ok: bool
    changed: bool
    message: str
    requirements: tuple[str, ...] = ()


Runner = Callable[[list[str], Path], CommandResult]


def find_git_root(start: Path) -> Path | None:
    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def run_git_update(
    project: Path,
    runner: Runner | None = None,
    check=None,
) -> UpdateOutcome:
    """Fast-forward to the newest commit on ``origin/main`` whose tests passed.

    Fetch once and remember that ``origin/main`` SHA. A release cut is pushed
    by the test workflow and has no run of its own until a later dispatch, so
    walk that SHA and its parents, newest first, and ``git merge --ff-only``
    the first one whose ``suit-o-tests.yml`` run succeeded. This never runs
    ``git pull`` and does not read ``origin/main`` again after the fetch.
    """

    run = runner or subprocess_runner
    status_of = check or github_check_state
    repo = find_git_root(project)
    if repo is None:
        return UpdateOutcome(False, False, "Suit-O could not find a git checkout to update.")
    head = run(["git", "rev-parse", "HEAD"], repo)
    if head.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(head.stdout + "\n" + head.stderr))
    fetched = run(["git", "fetch", "origin"], repo)
    if fetched.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(fetched.stdout + "\n" + fetched.stderr))
    remote = run(["git", "rev-parse", "origin/main"], repo)
    if remote.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(remote.stdout + "\n" + remote.stderr))
    before = head.stdout.strip()
    sha = remote.stdout.strip()
    if sha == before:
        return UpdateOutcome(True, False, "Already up to date.")
    chosen, refusal = _newest_tested_commit(run, status_of, repo, before, sha)
    if chosen is None:
        return UpdateOutcome(False, False, refusal)
    return _merge_ff_only(project, run, chosen, before)


def _newest_tested_commit(runner: Runner, status_of, repo: Path, before: str, sha: str) -> tuple[str | None, str]:
    """Return the newest passing SHA among ``sha`` and the commits behind it.

    ``sha`` is the ``origin/main`` value captured once. Parents come from
    ``git rev-list`` and are not a second read of the remote tip.
    """

    commits = [sha, *_older_commits(runner, repo, before, sha)]
    tip_state = "pending"
    for index, commit in enumerate(commits):
        try:
            state = str(status_of(commit))
        except OSError as exc:
            return None, f"Update stopped. Suit-O could not read the test result. {exc}"
        if index == 0:
            tip_state = state
        if state == "success":
            return commit, ""
    return None, explain_check_state(tip_state, sha)


def _older_commits(runner: Runner, repo: Path, before: str, sha: str) -> list[str]:
    listed = runner(["git", "rev-list", "--max-count", "20", f"{before}..{sha}"], repo)
    if listed.code != 0:
        return []
    return [line.strip() for line in listed.stdout.splitlines() if line.strip() and line.strip() != sha]


def _merge_ff_only(project: Path, runner: Runner, sha: str, before: str) -> UpdateOutcome:
    """Fast-forward to ``sha`` only. Does not fetch again and does not pull."""

    repo = find_git_root(project)
    if repo is None:
        return UpdateOutcome(False, False, "Suit-O could not find a git checkout to update.")
    merged = runner(["git", "merge", "--ff-only", sha], repo)
    combined = f"{merged.stdout}\n{merged.stderr}"
    if merged.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(combined))
    after = runner(["git", "rev-parse", "HEAD"], repo)
    if after.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(after.stdout + "\n" + after.stderr))
    landed = after.stdout.strip()
    if landed != sha:
        checked = sha.strip()[:7] or sha
        here = landed[:7] or "(none)"
        return UpdateOutcome(
            False,
            False,
            f"Update stopped. The checkout is {here}, not the checked commit {checked}.",
        )
    if landed == before or _already_current(combined):
        return UpdateOutcome(True, False, "Already up to date.")
    diff = runner(
        ["git", "diff", "--name-only", before, landed],
        repo,
    )
    files = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    requirements = select_requirements(
        requirement_paths(files, repo=repo, project=Path(project)),
        _installed_optional(Path(project)),
    )
    if requirements:
        names = ", ".join(Path(item).name for item in requirements)
        message = f"Updated. Reinstalling {names}, then reloading."
    else:
        message = "Updated. Suit-O will reload."
    return UpdateOutcome(True, True, message, tuple(requirements))


def install_requirements(
    paths: tuple[str, ...] | list[str],
    runner: Runner | None = None,
) -> str | None:
    """Install each requirements file. Returns a plain error, or None on success."""

    run = runner or subprocess_runner
    for raw in paths:
        path = Path(raw)
        result = run([sys.executable, "-m", "pip", "install", "-r", str(path)], path.parent)
        if result.code != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            tail = detail[-1] if detail else "pip failed"
            return f"Could not install {path.name}. {tail}"
    return None


def explain_check_state(state: str, sha: str) -> str:
    """Plain reason the Update button will not apply this commit."""

    short = sha.strip()[:7] or sha
    if state == "failure":
        return (
            f"Update stopped. Tests failed for commit {short}. "
            "Suit-O will not apply a commit whose tests did not pass."
        )
    return (
        f"Update stopped. Tests for commit {short} are still running or have not reported yet. "
        "Suit-O will not apply that commit until they pass."
    )


def interpret_workflow_runs(body: object, sha: str) -> str:
    """Map workflow-run JSON to success, failure, or pending.

    Only the ``suit-o-tests.yml`` run for ``sha`` counts. A check named
    pytest on some other workflow does not.
    """

    if not isinstance(body, dict):
        return "pending"
    runs = body.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        return "pending"
    wanted = sha.strip()
    matching = [
        run
        for run in runs
        if isinstance(run, dict) and _is_suit_o_workflow(run, wanted)
    ]
    if not matching:
        return "pending"
    newest = max(matching, key=_workflow_stamp)
    status = str(newest.get("status") or "").lower()
    conclusion = str(newest.get("conclusion") or "").lower()
    if status != "completed" or not conclusion:
        return "pending"
    if conclusion == "success":
        return "success"
    if conclusion in {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "stale",
        "startup_failure",
    }:
        return "failure"
    return "pending"


def github_check_state(sha: str) -> str:
    """Read the public workflow-run API for this SHA. No token."""

    import json
    import urllib.request

    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/actions/workflows/{SUIT_O_WORKFLOW}/runs?head_sha={sha}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "suit-o",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    return interpret_workflow_runs(body, sha)


def _is_suit_o_workflow(run: dict, sha: str) -> bool:
    path = str(run.get("path") or "").replace("\\", "/")
    if not path.endswith(SUIT_O_WORKFLOW):
        return False
    head = str(run.get("head_sha") or "").strip()
    return head == sha


def _workflow_stamp(run: dict) -> str:
    return str(run.get("updated_at") or run.get("created_at") or run.get("run_number") or "")


def explain_git_failure(text: str) -> str:
    """Turn git's refusal into one sentence a player can act on."""

    lowered = text.lower()
    if (
        "would be overwritten" in lowered
        or "local changes" in lowered
        or "please commit your changes or stash" in lowered
    ):
        files = _overwritten_files(text)
        listed = ", ".join(files) if files else "one or more files"
        return (
            f"Update stopped because {listed} has local edits that git would overwrite. "
            "Suit-O settings belong in config.local.yaml, which git ignores. "
            "Commit or stash the other edits, then press Update again."
        )
    if "not possible to fast-forward" in lowered or "diverging" in lowered:
        return (
            "Update stopped because this copy has commits that are not on the remote. "
            "Suit-O will not merge or rebase. Update this copy by hand."
        )
    first = next((line.strip() for line in text.splitlines() if line.strip()), "git merge failed")
    return f"Update failed. {first}"


def detect_installed_requirements() -> list[str]:
    """Optional requirement files whose packages are already on this machine.

    Uses module specs only. A broken install is not imported here.
    """

    found: list[str] = []
    if _module_present("chatterbox"):
        found.append("requirements-voice.txt")
    if _module_present("demucs") or _module_present("pyannote"):
        found.append("requirements-clips.txt")
    if _module_present("faster_whisper"):
        found.append("requirements-chat.txt")
    return found


def _module_present(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def select_requirements(paths: list[str], installed: set[str]) -> list[str]:
    """Keep base requirement files. Keep an optional file only if it is already installed."""

    chosen: list[str] = []
    for raw in paths:
        name = Path(raw).name
        if name in OPTIONAL_REQUIREMENTS and name not in installed:
            continue
        chosen.append(raw)
    return chosen


def _installed_optional(project: Path) -> set[str]:
    from suit_o.local_config import read_installed_requirements

    return read_installed_requirements(project / "config.yaml")


def requirement_paths(changed: list[str], *, repo: Path, project: Path) -> list[str]:
    """Requirements files inside the Suit-O project that this pull changed."""

    project_root = project.resolve()
    found: list[str] = []
    for raw in changed:
        candidate = (repo / raw).resolve()
        try:
            candidate.relative_to(project_root)
        except ValueError:
            continue
        if candidate.name in REQUIREMENT_NAMES and str(candidate) not in found:
            found.append(str(candidate))
    return found


def subprocess_runner(args: list[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")


def _already_current(text: str) -> bool:
    lowered = text.lower()
    return "already up to date" in lowered or "already up-to-date" in lowered


def _overwritten_files(text: str) -> list[str]:
    files: list[str] = []
    capture = False
    for line in text.splitlines():
        if "would be overwritten" in line.lower():
            capture = True
            continue
        if not capture:
            continue
        stripped = line.strip()
        if not stripped or stripped.lower().startswith(("please", "abort", "error:", "fatal:")):
            break
        files.append(stripped)
    return files
