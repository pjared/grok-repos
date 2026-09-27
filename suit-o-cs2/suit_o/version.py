"""The app version lives only in ``pyproject.toml``."""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

_VERSION_LINE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"\s*$')


class VersionError(ValueError):
    """pyproject.toml has no usable version."""


def version_file(project: Path | None = None) -> Path:
    root = PACKAGE_ROOT if project is None else Path(project)
    return root / "pyproject.toml"


def read_version(project: Path | None = None) -> str:
    """Return the ``[project].version`` string. This is the only copy."""

    path = version_file(project)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VersionError(f"Could not read {path.name}. {exc}") from exc
    match = _VERSION_LINE.search(text)
    if match is None:
        raise VersionError(f"{path.name} has no version = \"x.y.z\" line")
    return match.group(1).strip()


def write_version(text: str, version: str) -> str:
    """Replace the version line. The rest of the file stays put."""

    if _VERSION_LINE.search(text) is None:
        raise VersionError("pyproject.toml has no version = \"x.y.z\" line")
    return _VERSION_LINE.sub(f'version = "{version}"', text, count=1)
