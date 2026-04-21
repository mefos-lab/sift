#!/usr/bin/env python3
"""Bump the sift version in pyproject.toml, __init__.py, and CHANGELOG.md."""

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "sift" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"


def current_version() -> str:
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("Could not find version in pyproject.toml")
    return m.group(1)


def bump(version: str, level: str) -> str:
    parts = [int(x) for x in version.split(".")]
    if len(parts) != 3:
        raise SystemExit(f"Expected semver (X.Y.Z), got {version!r}")
    major, minor, patch = parts
    if level == "major":
        return f"{major + 1}.0.0"
    elif level == "minor":
        return f"{major}.{minor + 1}.0"
    elif level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise SystemExit(f"Unknown level {level!r} — use major, minor, or patch")


def update_pyproject(old: str, new: str) -> None:
    text = PYPROJECT.read_text()
    text = text.replace(f'version = "{old}"', f'version = "{new}"')
    PYPROJECT.write_text(text)


def update_init(old: str, new: str) -> None:
    text = INIT.read_text()
    text = text.replace(f'__version__ = "{old}"', f'__version__ = "{new}"')
    INIT.write_text(text)


def update_changelog(new: str) -> None:
    text = CHANGELOG.read_text()
    today = date.today().isoformat()
    text = text.replace(
        "## [Unreleased]",
        f"## [Unreleased]\n\n## [{new}] - {today}",
    )
    CHANGELOG.write_text(text)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("major", "minor", "patch"):
        print("Usage: bump_version.py <major|minor|patch>")
        raise SystemExit(1)

    level = sys.argv[1]
    old = current_version()
    new = bump(old, level)

    update_pyproject(old, new)
    update_init(old, new)
    update_changelog(new)

    print(f"{old} -> {new}")


if __name__ == "__main__":
    main()
