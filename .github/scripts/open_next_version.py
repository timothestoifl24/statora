"""Move develop on to the next version after a stable release.

A stable release tags vX.Y.Z from main, but develop keeps project.version X.Y.Z, so the next
push to develop fails: betas need the version they lead up to. This bumps pyproject.toml to the
next patch version X.Y.Z+1 and adds the empty "## [X.Y.Z+1] - Unreleased" section the changelog
collects the upcoming notes under. The beta build then warns that the section is empty until
someone writes them, and the release notes get the date. Bump further by hand (a minor or major
release) on the pull request this opens.

Does nothing when develop already holds another version, so re-running is safe.

Reads RELEASED_VERSION (X.Y.Z or vX.Y.Z), GITHUB_SERVER_URL and GITHUB_REPOSITORY; writes
bump, version and branch to GITHUB_OUTPUT (or stdout). Run from the repository root with
develop checked out.
"""

import os
import re
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
CHANGELOG = Path("CHANGELOG.md")
SEMVER = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
VERSION_LINE = re.compile(r'^version = "[^"]+"$', re.MULTILINE)
HEADING = re.compile(r"^## \[", re.MULTILINE)
LINK = re.compile(r"^\[(?P<version>[^\]]+)\]:\s*(?P<url>\S+)\s*$", re.MULTILINE)


def fail(message: str) -> None:
    print(f"::error::{message}")
    sys.exit(1)


def bump_pyproject(version: str) -> None:
    text = PYPROJECT.read_text()
    if not VERSION_LINE.search(text):
        fail("Could not find the 'version = \"X.Y.Z\"' line in pyproject.toml.")
    PYPROJECT.write_text(VERSION_LINE.sub(f'version = "{version}"', text, count=1))


def open_changelog_section(version: str) -> None:
    """Add the empty section for the upcoming version above the newest one, with its link."""
    text = CHANGELOG.read_text()
    heading = HEADING.search(text)
    if not heading:
        fail("CHANGELOG.md has no '## [X.Y.Z]' section to add the next version above.")
    text = text[: heading.start()] + f"## [{version}] - Unreleased\n\n" + text[heading.start() :]

    link = LINK.search(text)
    if link:
        # Reuse the newest link definition, so the URL keeps whatever shape the file already uses.
        url = link["url"].replace(link["version"], version).replace(f"v{link['version']}", f"v{version}")
        text = text[: link.start()] + f"[{version}]: {url}\n" + text[link.start() :]
    else:
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        text = text.rstrip("\n") + f"\n\n[{version}]: {server}/{repository}/releases/tag/v{version}\n"
    CHANGELOG.write_text(text)


def output(**values: str) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    if target := os.environ.get("GITHUB_OUTPUT"):
        with open(target, "a") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    released = os.environ.get("RELEASED_VERSION", "")
    match = SEMVER.match(released)
    if not match:
        print(f"::notice::{released!r} is not a stable X.Y.Z release; develop stays as it is.")
        return output(bump="false", version="", branch="")
    major, minor, patch = (int(part) for part in match.groups())

    current = tomllib.load(PYPROJECT.open("rb"))["project"]["version"]
    if current != f"{major}.{minor}.{patch}":
        print(f"::notice::develop is already on {current}, not the released {major}.{minor}.{patch}.")
        return output(bump="false", version="", branch="")

    version = f"{major}.{minor}.{patch + 1}"
    bump_pyproject(version)
    open_changelog_section(version)
    print(f"::notice::develop moves from {current} to {version}.")
    output(bump="true", version=version, branch=f"chore/open-{version}")


if __name__ == "__main__":
    main()
