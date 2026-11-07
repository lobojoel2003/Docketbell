"""Version and build metadata.

The semantic version lives in ``docketbell/__init__.py``. The build number,
commit and build date are injected at build time (CI sets them as Docker build
arguments) so that every running copy can say exactly what it is.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from docketbell import __version__


@dataclass(frozen=True)
class BuildInfo:
    version: str
    build: str
    commit: str
    built_at: str

    @property
    def label(self) -> str:
        """Human-readable label such as ``Docketbell 1.0.0 (build 42, 1a2b3c4)``."""
        details = [f"build {self.build}"] if self.build != "dev" else ["development build"]
        if self.commit:
            details.append(self.commit[:7])
        return f"Docketbell {self.version} ({', '.join(details)})"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _git_commit() -> str:
    repo = Path(__file__).resolve().parent.parent
    if not (repo / ".git").exists():
        return ""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - git on PATH is fine for dev builds
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    return BuildInfo(
        version=__version__,
        build=os.environ.get("DOCKETBELL_BUILD_NUMBER", "").strip() or "dev",
        commit=os.environ.get("DOCKETBELL_GIT_SHA", "").strip() or _git_commit(),
        built_at=os.environ.get("DOCKETBELL_BUILD_DATE", "").strip(),
    )
