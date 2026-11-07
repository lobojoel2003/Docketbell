"""Prepare a release: bump the version, date the changelog, commit and tag.

    python scripts/release.py 1.1.0
    git push origin main v1.1.0      # the Release workflow does the rest

Versions follow Semantic Versioning (https://semver.org). The tag push makes
GitHub Actions run the tests, publish ghcr.io/<owner>/docketbell:1.1.0 (plus
1.1, 1 and latest), and create a GitHub release with notes taken from
CHANGELOG.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "docketbell" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "https://github.com/lobojoel2003/Docketbell"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def current_version() -> str:
    match = re.search(r'__version__ = "(.+?)"', VERSION_FILE.read_text())
    if not match:
        sys.exit("Could not find __version__ in docketbell/__init__.py")
    return match.group(1)


def key(version: str) -> tuple:
    major, minor, patch, pre = SEMVER.match(version).groups()
    # A pre-release sorts before the release it leads up to.
    return int(major), int(minor), int(patch), pre is None, pre or ""


def update_changelog(text: str, old: str, new: str, today: str) -> str:
    if "## [Unreleased]" not in text:
        sys.exit("CHANGELOG.md needs an '## [Unreleased]' section.")
    body = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0].strip()
    if not body:
        sys.exit("The Unreleased section of CHANGELOG.md is empty. Describe the changes first.")
    text = text.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{new}] - {today}", 1)
    text = re.sub(
        r"^\[Unreleased\]: .*$",
        f"[Unreleased]: {REPO}/compare/v{new}...HEAD\n[{new}]: {REPO}/compare/v{old}...v{new}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    return text


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a Docketbell release.")
    parser.add_argument("version", help="New version, e.g. 1.1.0 or 1.1.0-rc.1")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change.")
    parser.add_argument("--no-git", action="store_true", help="Edit files only; no commit or tag.")
    args = parser.parse_args()

    new = args.version.removeprefix("v")
    if not SEMVER.match(new):
        sys.exit(f"{new!r} is not a semantic version like 1.2.3")
    old = current_version()
    if key(new) <= key(old):
        sys.exit(f"{new} must be newer than the current version {old}")

    today = dt.date.today().isoformat()
    changelog = update_changelog(CHANGELOG.read_text(), old, new, today)
    version_file = VERSION_FILE.read_text().replace(
        f'__version__ = "{old}"', f'__version__ = "{new}"'
    )
    if args.dry_run:
        print(f"Would release {old} -> {new} ({today}) and tag v{new}.")
        return

    VERSION_FILE.write_text(version_file)
    CHANGELOG.write_text(changelog)
    print(f"Updated version {old} -> {new} and dated the changelog.")
    if args.no_git:
        return
    git("add", str(VERSION_FILE), str(CHANGELOG))
    git("commit", "-m", f"Release v{new}")
    git("tag", "-a", f"v{new}", "-m", f"Docketbell {new}")
    print(f"Committed and tagged v{new}. Publish it with:\n\n    git push origin main v{new}\n")


if __name__ == "__main__":
    main()
