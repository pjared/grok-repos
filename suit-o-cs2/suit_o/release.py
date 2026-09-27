"""Cut a Suit-O version on main.

The Update button does not call this. It only pulls. This step runs after
tests pass on main, or when a maintainer passes ``--commit`` while pushing.
An empty Unreleased section does nothing, so a cut does not cut again.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from suit_o.changelog import ChangelogError, cut_unreleased
from suit_o.update import find_git_root
from suit_o.version import PACKAGE_ROOT, read_version, version_file, write_version

TAG_PREFIX = "suit-o-v"
_PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific_today() -> str:
    return datetime.now(_PACIFIC).date().isoformat()


def tag_name(version: str) -> str:
    return f"{TAG_PREFIX}{version}"


def cut_working_tree(project: Path | None = None, *, today: str | None = None) -> str | None:
    """Rewrite the changelog and pyproject.toml. Return the new version, or None."""

    root = PACKAGE_ROOT if project is None else Path(project)
    changelog_path = root / "CHANGELOG.md"
    pyproject_path = version_file(root)
    changelog = changelog_path.read_text(encoding="utf-8")
    current = read_version(root)
    cut = cut_unreleased(changelog, today=today or pacific_today(), current_version=current)
    if cut is None:
        return None
    updated, version = cut
    changelog_path.write_text(updated, encoding="utf-8")
    pyproject_path.write_text(
        write_version(pyproject_path.read_text(encoding="utf-8"), version),
        encoding="utf-8",
    )
    return version


def commit_and_tag(project: Path, version: str) -> None:
    """Commit the two release files and tag ``suit-o-vX.Y.Z``. Does not push."""

    repo = find_git_root(project)
    if repo is None:
        raise ChangelogError("Could not find the git checkout to tag")
    _git_identity(repo)
    changelog = project / "CHANGELOG.md"
    pyproject = version_file(project)
    _run(["git", "add", "--", str(changelog), str(pyproject)], repo)
    _run(["git", "commit", "-m", f"Cut Suit-O {version}."], repo)
    _run(["git", "tag", tag_name(version)], repo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut the Unreleased changelog into a version.")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit the changelog and pyproject.toml, and tag suit-o-vX.Y.Z. Does not push.",
    )
    parser.add_argument("--project", type=Path, default=PACKAGE_ROOT)
    args = parser.parse_args(argv)
    try:
        version = cut_working_tree(args.project)
    except (ChangelogError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if version is None:
        print("Unreleased is empty. No release cut.")
        return 0
    print(f"Cut {version}.")
    if args.commit:
        try:
            commit_and_tag(args.project, version)
        except (ChangelogError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Tagged {tag_name(version)}.")
    return 0


def _git_identity(repo: Path) -> None:
    """GitHub Actions has no commit identity until this sets one."""

    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    _run(["git", "config", "user.name", "github-actions[bot]"], repo)
    _run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], repo)


def _run(args: list[str], cwd: Path) -> None:
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ChangelogError(detail or "git failed")


if __name__ == "__main__":
    raise SystemExit(main())
