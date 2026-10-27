"""Delete the betas that a stable release has superseded.

Releasing X.Y.Z removes every beta A.B.C-beta.N with A.B.C <= X.Y.Z (so 1.2.1 removes
1.1.2-beta.*, 1.2.0-beta.* and 1.2.1-beta.*). Betas of newer versions stay. For each beta it
deletes:
- the container image, with the untagged platform images and attestation manifests behind it
  (unless a kept image still uses them). An image version that carries any tag other than its
  beta, "beta", "sha-*" or an attestation tag is never touched,
- the GitHub pre-release vA.B.C-beta.N and its git tag.

Reads RELEASE_VERSION (X.Y.Z or vX.Y.Z), OWNER, REPOSITORY (owner/name), PACKAGE, GH_TOKEN and
DRY_RUN ("true" only lists what would be deleted). Needs a token with packages: write and
contents: write, and the repository must have the Admin role on the package (package settings →
Manage Actions access). The GHCR helpers live in ghcr.py.
"""

import os
import re
import urllib.error

from ghcr import API, delete_versions, package_versions, paginate, report, request, tags, with_orphans

SEMVER = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
BETA = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-beta\.\d+$")
DISPOSABLE = re.compile(r"^(beta|sha-[0-9a-f]+|sha256-[0-9a-f]{64}(\.\w+)?)$")


def superseded(name: str, released: tuple[int, ...]) -> bool:
    match = BETA.match(name.removeprefix("v"))
    return bool(match) and tuple(int(part) for part in match.groups()) <= released


def clean_images(owner: str, package: str, token: str, released: tuple[int, ...], dry_run: bool) -> None:
    base, versions = package_versions(owner, package, token)

    doomed: dict[int, dict] = {}
    for version in versions:
        names = tags(version)
        betas = [t for t in names if superseded(t, released)]
        if not betas:
            continue
        if others := [t for t in names if not BETA.match(t) and not DISPOSABLE.match(t)]:
            print(f"::warning::Keeping image {', '.join(betas)}: it also carries {', '.join(others)}.")
            continue
        doomed[version["id"]] = version

    with_orphans(doomed, versions, owner, package, token)
    entries = delete_versions(base, doomed, token, dry_run)
    report(f"{'Would delete' if dry_run else 'Deleted'} {len(doomed)} image versions", entries)


def clean_releases(repository: str, token: str, released: tuple[int, ...], dry_run: bool) -> None:
    base = f"{API}/repos/{repository}"
    releases = {
        r["tag_name"]: r for r in paginate(f"{base}/releases", token) if superseded(r["tag_name"], released)
    }
    refs = request(f"{base}/git/matching-refs/tags/v", token)[0]
    tags = sorted(
        {ref["ref"].removeprefix("refs/tags/") for ref in refs} | set(releases),
        key=lambda t: [int(p) for p in re.findall(r"\d+", t)],
    )
    tags = [t for t in tags if superseded(t, released)]

    entries = []
    for tag in tags:
        entries.append(f"- `{tag}`{' (pre-release and tag)' if tag in releases else ' (tag only)'}")
        if dry_run:
            continue
        if tag in releases:
            request(f"{base}/releases/{releases[tag]['id']}", token, method="DELETE")
        try:
            request(f"{base}/git/refs/tags/{tag}", token, method="DELETE")
        except urllib.error.HTTPError as error:
            if error.code != 422:  # already gone
                raise
    report(f"{'Would delete' if dry_run else 'Deleted'} {len(tags)} beta releases and tags", entries)


def main() -> None:
    release = os.environ.get("RELEASE_VERSION", "")
    owner = os.environ["OWNER"]
    repository = os.environ["REPOSITORY"]
    package = os.environ.get("PACKAGE", "statora")
    token = os.environ["GH_TOKEN"]
    dry_run = os.environ.get("DRY_RUN", "false") == "true"

    match = SEMVER.match(release)
    if not match:
        print(f"::notice::{release!r} is not a stable X.Y.Z release; nothing to clean up.")
        return
    released = tuple(int(part) for part in match.groups())

    # Releases and tags first: they don't depend on the package permission the images need.
    clean_releases(repository, token, released, dry_run)
    clean_images(owner, package, token, released, dry_run)


if __name__ == "__main__":
    main()
