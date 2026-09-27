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
)

GITHUB_OWNER = "pjared"
GITHUB_REPO = "grok-repos"
SUIT_O_CHECK_MARKERS = ("pytest", "suit-o")


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
    """Fast-forward only onto a commit whose Suit-O tests passed.

    A stub ``runner`` without ``check`` keeps the older pull-only path so
    existing tests can exercise git errors without calling GitHub. The
    desktop window passes neither and always checks the public API first.
    """

    if check is None and runner is not None:
        return _pull_ff_only(project, runner)
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
    if remote.stdout.strip() == head.stdout.strip():
        return UpdateOutcome(True, False, "Already up to date.")
    sha = remote.stdout.strip()
    try:
        state = status_of(sha)
    except OSError as exc:
        return UpdateOutcome(False, False, f"Update stopped. Suit-O could not read the test result. {exc}")
    if state != "success":
        return UpdateOutcome(False, False, explain_check_state(str(state), sha))
    return _pull_ff_only(project, run)


def _pull_ff_only(project: Path, runner: Runner | None = None) -> UpdateOutcome:
    """Run ``git pull --ff-only``. Already up to date does not ask for a restart."""

    repo = find_git_root(project)
    if repo is None:
        return UpdateOutcome(False, False, "Suit-O could not find a git checkout to update.")
    run = runner or subprocess_runner
    before = run(["git", "rev-parse", "HEAD"], repo)
    if before.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(before.stdout + "\n" + before.stderr))
    pull = run(["git", "pull", "--ff-only"], repo)
    combined = f"{pull.stdout}\n{pull.stderr}"
    if pull.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(combined))
    if _already_current(combined):
        return UpdateOutcome(True, False, "Already up to date.")
    after = run(["git", "rev-parse", "HEAD"], repo)
    if after.code != 0:
        return UpdateOutcome(False, False, explain_git_failure(after.stdout + "\n" + after.stderr))
    if after.stdout.strip() == before.stdout.strip():
        return UpdateOutcome(True, False, "Already up to date.")
    diff = run(
        ["git", "diff", "--name-only", before.stdout.strip(), after.stdout.strip()],
        repo,
    )
    files = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    requirements = requirement_paths(files, repo=repo, project=Path(project))
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


def interpret_check_runs(body: object) -> str:
    """Map GitHub check-run JSON to success, failure, or pending.

    Only Suit-O's pytest check counts. Other workflows in the monorepo do not.
    """

    if not isinstance(body, dict):
        return "pending"
    runs = body.get("check_runs")
    if not isinstance(runs, list) or not runs:
        return "pending"
    relevant = [run for run in runs if isinstance(run, dict) and _is_suit_o_check(run)]
    if not relevant:
        return "pending"
    saw_success = False
    for run in relevant:
        status = str(run.get("status") or "").lower()
        conclusion = str(run.get("conclusion") or "").lower()
        if status != "completed" or not conclusion:
            return "pending"
        if conclusion in {"failure", "cancelled", "timed_out", "action_required", "stale"}:
            return "failure"
        if conclusion == "success":
            saw_success = True
            continue
        if conclusion in {"skipped", "neutral"}:
            continue
        return "pending"
    return "success" if saw_success else "pending"


def github_check_state(sha: str) -> str:
    """Read the public check-runs API. No token; the repository is public."""

    import json
    import urllib.request

    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/commits/{sha}/check-runs"
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
    return interpret_check_runs(body)


def _is_suit_o_check(run: dict) -> bool:
    name = str(run.get("name") or "").lower()
    return any(marker in name for marker in SUIT_O_CHECK_MARKERS)


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
    first = next((line.strip() for line in text.splitlines() if line.strip()), "git pull failed")
    return f"Update failed. {first}"


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
