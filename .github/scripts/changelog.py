"""Read sections of CHANGELOG.md (Keep a Changelog format: "## [X.Y.Z] - YYYY-MM-DD" or "- Unreleased").

    python3 .github/scripts/changelog.py section 0.2.0-beta.3   # prints the 0.2.0 section's body
    python3 .github/scripts/changelog.py check 0.2.0 --released  # fails unless 0.2.0 has a date
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path("CHANGELOG.md")
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?:\s+-\s+(?P<date>.+?))?\s*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def base_version(version: str) -> str:
    """0.2.0-beta.3 → 0.2.0: betas show the notes of the release they lead up to."""
    return version.split("-", 1)[0].lstrip("v")


def find(version: str, text: str | None = None) -> tuple[str | None, str] | None:
    """(date, body) of the section for this version, or None if there is no such section."""
    text = CHANGELOG.read_text() if text is None else text
    wanted = base_version(version)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = HEADING.match(line)
        if not match or match["version"] != wanted:
            continue
        body = []
        for following in lines[i + 1 :]:
            # The section ends at the next version heading or the link definitions at the bottom.
            if following.startswith("## ") or re.match(r"^\[[^\]]+\]:\s", following):
                break
            body.append(following)
        return match["date"], "\n".join(body).strip()
    return None


def problem(version: str, released: bool, text: str | None = None) -> str | None:
    """Why the changelog isn't ready for this version, or None if it is."""
    found = find(version, text)
    wanted = base_version(version)
    if found is None:
        return f"CHANGELOG.md has no section for {wanted}. Add '## [{wanted}] - Unreleased' with the changes."
    date, body = found
    if not body:
        return f"The {wanted} section in CHANGELOG.md is empty."
    if released and not (date and DATE.match(date)):
        return (
            f"The {wanted} section in CHANGELOG.md has no release date ({date or 'none'}). "
            f"Change it to '## [{wanted}] - YYYY-MM-DD' before releasing."
        )
    return None


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "section":
        found = find(argv[1])
        if found is None:
            print(f"::warning::CHANGELOG.md has no section for {base_version(argv[1])}", file=sys.stderr)
            return 1
        print(found[1])
        return 0
    if len(argv) >= 2 and argv[0] == "check":
        message = problem(argv[1], released="--released" in argv)
        if message:
            print(f"::error::{message}")
            return 1
        print(f"CHANGELOG.md is ready for {base_version(argv[1])}.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
