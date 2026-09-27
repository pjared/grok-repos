"""Changelog parsing and the slice of versions an update should show."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest

from suit_o.changelog import (
    ChangelogError,
    ReleaseNotes,
    bump_version,
    changes_between,
    cut_unreleased,
    format_whats_new,
    parse_changelog,
)
from suit_o.gui.news import WhatsNew
from suit_o.version import PACKAGE_ROOT, read_version, write_version

_SAMPLE = """\
# Changelog

## [Unreleased]

### Added

- A window version.

## [0.2.0] - 2026-09-27

### Added

- Chat.

### Fixed

- A typo in the hint.

## [0.1.1] - 2026-09-26

### Fixed

- The update checkbox.

## [0.1.0] - 2026-09-26

### Added

- Suit-O.
"""


def _shipped() -> list[ReleaseNotes]:
    text = (PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return parse_changelog(text)


def test_parse_changelog_keeps_sections_and_rejects_a_bad_version():
    notes = parse_changelog(_SAMPLE)
    assert [item.version for item in notes] == ["Unreleased", "0.2.0", "0.1.1", "0.1.0"]
    assert notes[1].date == "2026-09-27"
    assert notes[1].sections["Added"] == ("Chat.",)
    assert notes[1].sections["Fixed"] == ("A typo in the hint.",)
    assert notes[0].sections["Added"] == ("A window version.",)
    with pytest.raises(ChangelogError):
        parse_changelog("## [1.2] - 2026-09-27\n\n### Added\n\n- Nope.\n")
    with pytest.raises(ChangelogError):
        parse_changelog("# Changelog\n\nNo headings.\n")


def test_changes_between_is_newest_first_and_skips_unreleased():
    notes = parse_changelog(_SAMPLE)
    assert [item.version for item in changes_between(notes, "0.1.0", "0.2.0")] == ["0.2.0", "0.1.1"]
    assert changes_between(notes, "0.2.0", "0.1.0") == []
    assert changes_between(notes, "0.1.1", "0.1.1") == []
    patch = changes_between(notes, "0.1.0", "0.1.1")
    assert [item.version for item in patch] == ["0.1.1"]
    assert "Fixed" in patch[0].sections
    assert all(item.version != "Unreleased" for item in changes_between(notes, "0.0.0", "9.9.9"))
    text = format_whats_new(changes_between(notes, "0.1.1", "0.2.0"))
    assert text.startswith("0.2.0 — 2026-09-27")
    assert "\nAdded\n- Chat." in text
    assert "Unreleased" not in text
    assert format_whats_new([]) == "Nothing new."


def test_shipped_history_starts_at_0_1_0_and_matches_pyproject():
    notes = _shipped()
    released = [item for item in notes if item.version != "Unreleased"]
    versions = [item.version for item in released]
    assert notes[0].version == "Unreleased"
    assert versions[0] == read_version()
    assert "0.17.0" in versions
    assert versions[-1] == "0.1.0"
    assert versions == sorted(versions, key=lambda item: tuple(int(part) for part in item.split(".")), reverse=True)
    chat = changes_between(notes, "0.13.0", "0.15.0")
    assert [item.version for item in chat] == ["0.15.0", "0.14.0"]
    fix = changes_between(notes, "0.12.0", "0.12.1")
    assert [item.version for item in fix] == ["0.12.1"]
    assert list(fix[0].sections) == ["Fixed"]
    assert changes_between(notes, "0.16.0", "0.15.0") == []
    assert all(item.version != "Unreleased" for item in changes_between(notes, "0.1.0", read_version()))


def test_bump_and_cut_leave_an_empty_unreleased_section():
    added = ReleaseNotes("Unreleased", sections={"Added": ("A button.",)})
    changed = ReleaseNotes("Unreleased", sections={"Changed": ("The overlay.",)})
    removed = ReleaseNotes("Unreleased", sections={"Removed": ("The daily file.",)})
    fixed = ReleaseNotes("Unreleased", sections={"Fixed": ("A crash.",)})
    both = ReleaseNotes("Unreleased", sections={"Added": ("A button.",), "Fixed": ("A crash.",)})
    assert bump_version("0.17.0", added) == "0.18.0"
    assert bump_version("0.17.0", changed) == "0.18.0"
    assert bump_version("0.17.0", removed) == "0.18.0"
    assert bump_version("0.12.0", fixed) == "0.12.1"
    assert bump_version("1.4.2", both) == "1.5.0"
    with pytest.raises(ChangelogError):
        bump_version("0.1.0", ReleaseNotes("Unreleased"))

    empty = "## [Unreleased]\n\n## [0.1.0] - 2026-09-26\n\n### Added\n\n- Suit-O.\n"
    assert cut_unreleased(empty, today="2026-09-27", current_version="0.1.0") is None
    cut = cut_unreleased(_SAMPLE, today="2026-09-27", current_version="0.2.0")
    assert cut is not None
    text, version = cut
    assert version == "0.3.0"
    again = parse_changelog(text)
    assert again[0].version == "Unreleased"
    assert again[0].empty()
    assert again[1].version == "0.3.0"
    assert again[1].date == "2026-09-27"
    assert again[1].sections["Added"] == ("A window version.",)
    assert cut_unreleased(text, today="2026-09-27", current_version="0.3.0") is None


def test_write_version_replaces_only_the_version_line():
    source = '[project]\nname = "suit-o"\nversion = "0.17.0"\ndescription = "version = \\"nope\\""\n'
    updated = write_version(source, "0.18.0")
    assert 'version = "0.18.0"' in updated
    assert 'version = "0.17.0"' not in updated
    assert 'description = "version = \\"nope\\""' in updated


def test_whats_new_panel_shows_the_added_section():
    root = tk.Tk()
    root.withdraw()
    try:
        notes = [ReleaseNotes("0.18.0", "2026-09-27", {"Added": ("The window shows the version.",)})]
        panel = WhatsNew(root, "What's new", notes)
        text = panel.body.get("1.0", "end")
        assert "0.18.0 — 2026-09-27" in text
        assert "Added" in text
        assert "The window shows the version." in text
        panel.window.destroy()
    finally:
        root.destroy()


def test_cut_working_tree_skips_an_empty_unreleased_section(tmp_path: Path):
    from suit_o.release import cut_working_tree

    project = tmp_path / "suit-o-cs2"
    project.mkdir()
    changelog = project / "CHANGELOG.md"
    pyproject = project / "pyproject.toml"
    changelog.write_text(
        "## [Unreleased]\n\n## [0.1.0] - 2026-09-26\n\n### Added\n\n- Suit-O.\n",
        encoding="utf-8",
    )
    pyproject.write_text('version = "0.1.0"\n', encoding="utf-8")
    before = changelog.read_text(encoding="utf-8")
    assert cut_working_tree(project, today="2026-09-27") is None
    assert changelog.read_text(encoding="utf-8") == before
    assert read_version(project) == "0.1.0"

    changelog.write_text(_SAMPLE, encoding="utf-8")
    pyproject.write_text('version = "0.2.0"\n', encoding="utf-8")
    assert cut_working_tree(project, today="2026-09-27") == "0.3.0"
    assert read_version(project) == "0.3.0"
    notes = parse_changelog(changelog.read_text(encoding="utf-8"))
    assert notes[0].empty()
    assert notes[1].version == "0.3.0"
