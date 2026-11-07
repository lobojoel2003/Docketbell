"""The release helper keeps the version, changelog and tag in step."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release.py"
spec = importlib.util.spec_from_file_location("release_script", SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

CHANGELOG = """# Changelog

## [Unreleased]

### Added
- Something new.

## [1.0.0] - 2026-11-07

First release.

[Unreleased]: https://github.com/lobojoel2003/Docketbell/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lobojoel2003/Docketbell/releases/tag/v1.0.0
"""


def test_version_ordering():
    assert release.key("1.0.1") > release.key("1.0.0")
    assert release.key("1.1.0-rc.1") < release.key("1.1.0")
    assert release.key("2.0.0") > release.key("1.99.99")


def test_changelog_is_dated_and_linked():
    text = release.update_changelog(CHANGELOG, "1.0.0", "1.1.0", "2026-12-01")
    assert "## [Unreleased]\n\n## [1.1.0] - 2026-12-01\n\n### Added" in text
    assert "[Unreleased]: https://github.com/lobojoel2003/Docketbell/compare/v1.1.0...HEAD" in text
    assert "[1.1.0]: https://github.com/lobojoel2003/Docketbell/compare/v1.0.0...v1.1.0" in text


def test_empty_unreleased_section_is_refused():
    empty = CHANGELOG.replace("### Added\n- Something new.\n\n", "")
    with pytest.raises(SystemExit):
        release.update_changelog(empty, "1.0.0", "1.1.0", "2026-12-01")


def test_current_version_matches_package():
    from docketbell import __version__

    assert release.current_version() == __version__


def test_changelog_has_a_section_for_the_current_version():
    from docketbell import __version__

    changelog = (SCRIPT.parent.parent / "CHANGELOG.md").read_text()
    assert f"## [{__version__}]" in changelog
