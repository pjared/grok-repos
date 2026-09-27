"""Read Keep a Changelog notes and the slice between two versions.

The Update button only reads this. Cutting a version happens on main.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTIONS = ("Added", "Changed", "Fixed", "Removed")

_HEADER = re.compile(r"^## \[([^\]\n]+)\](?:\s+-\s+(\d{4}-\d{2}-\d{2}))?\s*$")
_SECTION = re.compile(r"^### (Added|Changed|Fixed|Removed)\s*$")
_BULLET = re.compile(r"^- (.*\S)\s*$")
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class ChangelogError(ValueError):
    """The changelog text is not a version Suit-O can read."""


@dataclass(frozen=True)
class ReleaseNotes:
    """One version, or the Unreleased block. Sections keep file order."""

    version: str
    date: str = ""
    sections: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def empty(self) -> bool:
        return not any(self.sections.values())


def parse_changelog(text: str) -> list[ReleaseNotes]:
    """Releases in file order, which is newest first. Unreleased is included."""

    notes: list[ReleaseNotes] = []
    version = ""
    date = ""
    sections: dict[str, list[str]] = {}
    current = ""
    seen_header = False

    def flush() -> None:
        if not seen_header:
            return
        notes.append(
            ReleaseNotes(
                version=version,
                date=date,
                sections={name: tuple(items) for name, items in sections.items() if items},
            )
        )

    for raw in text.splitlines():
        header = _HEADER.match(raw.strip())
        if header:
            flush()
            seen_header = True
            version = header.group(1).strip()
            date = (header.group(2) or "").strip()
            if version != "Unreleased" and _VERSION.fullmatch(version) is None:
                raise ChangelogError(f"Version {version!r} is not x.y.z or Unreleased")
            sections = {}
            current = ""
            continue
        if not seen_header:
            continue
        section = _SECTION.match(raw.strip())
        if section:
            current = section.group(1)
            sections.setdefault(current, [])
            continue
        bullet = _BULLET.match(raw.strip())
        if bullet and current:
            sections[current].append(bullet.group(1).strip())
    flush()
    if not notes:
        raise ChangelogError("CHANGELOG.md has no ## [Unreleased] or ## [x.y.z] headings")
    return notes


def parse_semver(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(value.strip())
    if match is None:
        raise ChangelogError(f"Version {value!r} is not x.y.z")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def changes_between(notes: list[ReleaseNotes], old: str, new: str) -> list[ReleaseNotes]:
    """Versions after ``old`` through ``new``, newest first.

    ``old`` itself is not included. Unreleased is not a released version.
    An empty list means nothing changed in that range.
    """

    start = parse_semver(old)
    end = parse_semver(new)
    if end <= start:
        return []
    chosen = [
        item
        for item in notes
        if item.version != "Unreleased" and start < parse_semver(item.version) <= end
    ]
    chosen.sort(key=lambda item: parse_semver(item.version), reverse=True)
    return chosen


def bump_version(current: str, notes: ReleaseNotes) -> str:
    """Minor bump when a release adds, changes, or removes. Patch when it only fixes."""

    if notes.empty():
        raise ChangelogError("Unreleased has no notes")
    major, minor, patch = parse_semver(current)
    kinds = {name for name, items in notes.sections.items() if items}
    if kinds & {"Added", "Changed", "Removed"}:
        return f"{major}.{minor + 1}.0"
    if "Fixed" in kinds:
        return f"{major}.{minor}.{patch + 1}"
    raise ChangelogError("Unreleased has no notes")


def unreleased_notes(notes: list[ReleaseNotes]) -> ReleaseNotes | None:
    for item in notes:
        if item.version == "Unreleased":
            return item
    return None


def format_whats_new(notes: list[ReleaseNotes]) -> str:
    """Plain text for the What's new panel."""

    if not notes:
        return "Nothing new."
    blocks: list[str] = []
    for item in notes:
        title = item.version if not item.date else f"{item.version} — {item.date}"
        lines = [title, ""]
        for name in SECTIONS:
            bullets = item.sections.get(name) or ()
            if not bullets:
                continue
            lines.append(name)
            lines.extend(f"- {bullet}" for bullet in bullets)
            lines.append("")
        blocks.append("\n".join(lines).strip())
    return "\n\n".join(blocks)


def cut_unreleased(changelog: str, *, today: str, current_version: str) -> tuple[str, str] | None:
    """Move Unreleased under a new version heading. ``None`` when it is empty.

    ``today`` is ``YYYY-MM-DD`` in Pacific Time. The caller writes the files.
    """

    match = re.search(r"(?ms)^## \[Unreleased\]\s*\n(.*?)(?=^## \[|\Z)", changelog)
    if match is None:
        raise ChangelogError("CHANGELOG.md has no ## [Unreleased] section")
    body = match.group(1).strip("\n")
    parsed = parse_changelog("## [Unreleased]\n" + body + "\n")
    pending = unreleased_notes(parsed)
    if pending is None or pending.empty():
        return None
    version = bump_version(current_version, pending)
    if any(item.version == version for item in parse_changelog(changelog)):
        raise ChangelogError(f"{version} is already in the changelog")
    replacement = f"## [Unreleased]\n\n## [{version}] - {today}\n\n{body.strip()}\n\n"
    updated = changelog[: match.start()] + replacement + changelog[match.end() :]
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    if not updated.endswith("\n"):
        updated += "\n"
    return updated, version
