"""Tell whether a push or pull request only changes documentation.

Documentation-only changes skip the tests, the image build and any image or beta on develop and in
pull requests other than into main (see ci.yml, docker.yml and release_version.py); pages.yml builds
the docs for them. main and manual runs always do the full run.

Reads GITHUB_EVENT_NAME, GITHUB_REF, GITHUB_BASE_REF, and CHANGES_BASE and CHANGES_HEAD (the
commits to compare: the whole pull request, or everything a push brought). Run as a script, it
writes docs_only=true|false to GITHUB_OUTPUT (or stdout). Needs the full history fetched.
"""

import os
import re
import subprocess

# Files that never reach the tests or what the image does: the docs site with its toolchain, and
# Markdown at the top level (README.md is copied into the image, but only as package metadata).
# Anything else, .github/ included, gets the full run.
DOCS_ONLY = re.compile(r"^(docs/|[^/]+\.md$)")


def changed_files() -> list[str] | None:
    """Files changed between CHANGES_BASE and CHANGES_HEAD, or None when that can't be told."""
    base, head = os.environ.get("CHANGES_BASE", ""), os.environ.get("CHANGES_HEAD", "")
    if not base or not head or set(base) == {"0"}:  # a new branch has no "before"
        return None
    diff = subprocess.run(["git", "diff", "--name-only", f"{base}...{head}"], capture_output=True, text=True)
    if diff.returncode != 0:  # e.g. a force push dropped the old commit
        print(f"::warning::Could not compare {base[:7]}...{head[:7]}; running everything.")
        return None
    return diff.stdout.split()


def skippable() -> bool:
    """Only pushes to develop and pull requests not into main may skip anything."""
    event, ref = os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("GITHUB_REF", "")
    return (event == "push" and ref == "refs/heads/develop") or (
        event == "pull_request" and os.environ.get("GITHUB_BASE_REF") != "main"
    )


def docs_only() -> bool:
    if not skippable():
        return False
    files = changed_files()
    return bool(files) and all(DOCS_ONLY.match(name) for name in files)


def main() -> None:
    result = docs_only()
    if result:
        print("::notice::Only documentation changed: tests and the image build are skipped.")
    line = f"docs_only={'true' if result else 'false'}"
    if target := os.environ.get("GITHUB_OUTPUT"):
        with open(target, "a") as fh:
            fh.write(line + "\n")
    print(line)


if __name__ == "__main__":
    main()
