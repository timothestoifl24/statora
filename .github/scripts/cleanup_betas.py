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
Manage Actions access).
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
SEMVER = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
BETA = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-beta\.\d+$")
DISPOSABLE = re.compile(r"^(beta|sha-[0-9a-f]+|sha256-[0-9a-f]{64}(\.\w+)?)$")
INDEX_TYPES = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def fail(message: str) -> None:
    print(f"::error::{message}")
    sys.exit(1)


def request(
    url: str,
    token: str,
    method: str = "GET",
    accept: str = "application/vnd.github+json",
    basic: bool = False,
):
    auth = f"Basic {token}" if basic else f"Bearer {token}"
    req = urllib.request.Request(url, method=method, headers={"Authorization": auth, "Accept": accept})
    with urllib.request.urlopen(req) as response:
        body = response.read()
        return (json.loads(body) if body else None), response.headers


def paginate(url: str, token: str) -> list[dict]:
    items, url = [], f"{url}?per_page=100"
    while url:
        page, headers = request(url, token)
        items += page
        url = next(
            (
                part.split(";")[0].strip("<> ")
                for part in headers.get("Link", "").split(",")
                if 'rel="next"' in part
            ),
            None,
        )
    return items


def registry_token(owner: str, package: str, token: str) -> str:
    basic = base64.b64encode(f"{owner}:{token}".encode()).decode()
    url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{owner}/{package}:pull"
    return request(url, basic, basic=True)[0]["token"]


def children(owner: str, package: str, digest: str, token: str) -> set[str]:
    """Digests an image index points to (platform images, attestation manifests)."""
    url = f"https://ghcr.io/v2/{owner}/{package}/manifests/{digest}"
    try:
        manifest = request(url, token, accept=INDEX_TYPES)[0]
    except urllib.error.HTTPError as error:
        print(f"::warning::Could not read manifest {digest}: {error}")
        return set()
    return {entry["digest"] for entry in manifest.get("manifests", [])}


def superseded(name: str, released: tuple[int, ...]) -> bool:
    match = BETA.match(name.removeprefix("v"))
    return bool(match) and tuple(int(part) for part in match.groups()) <= released


def report(title: str, entries: list[str]) -> None:
    lines = [f"### {title}", "", *(entries or ["_Nothing to delete._"]), ""]
    print("\n".join(lines))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as fh:
            fh.write("\n".join(lines) + "\n")


def clean_images(owner: str, package: str, token: str, released: tuple[int, ...], dry_run: bool) -> None:
    kind = "orgs" if request(f"{API}/users/{owner}", token)[0]["type"] == "Organization" else "users"
    base = f"{API}/{kind}/{owner}/packages/container/{package}/versions"
    versions = paginate(base, token)
    tags = {v["id"]: v["metadata"]["container"]["tags"] for v in versions}

    doomed: dict[int, dict] = {}
    for version in versions:
        names = tags[version["id"]]
        betas = [t for t in names if superseded(t, released)]
        if not betas:
            continue
        if others := [t for t in names if not BETA.match(t) and not DISPOSABLE.match(t)]:
            print(f"::warning::Keeping image {', '.join(betas)}: it also carries {', '.join(others)}.")
            continue
        doomed[version["id"]] = version

    # Attestations pushed next to an image are tagged sha256-<digest of that image>.
    doomed_digests = {v["name"] for v in doomed.values()}
    for version in versions:
        if any(t.split(".")[0].replace("sha256-", "sha256:") in doomed_digests for t in tags[version["id"]]):
            doomed.setdefault(version["id"], version)

    # Untagged platform images and attestation manifests behind the deleted indexes, unless a
    # kept tagged version still points to them.
    if doomed:
        registry = registry_token(owner, package, token)
        orphans: set[str] = set()
        for version in doomed.values():
            orphans |= children(owner, package, version["name"], registry)
        for version in versions:
            if version["id"] not in doomed and tags[version["id"]]:
                orphans -= children(owner, package, version["name"], registry)
        for version in versions:
            if version["name"] in orphans and not tags[version["id"]]:
                doomed.setdefault(version["id"], version)

    entries = []
    for version in sorted(doomed.values(), key=lambda v: v["created_at"]):
        entries.append(f"- `{version['name'][:19]}` {', '.join(tags[version['id']]) or 'untagged'}")
        if not dry_run:
            try:
                request(f"{base}/{version['id']}", token, method="DELETE")
            except urllib.error.HTTPError as error:
                report("Images (stopped)", entries)
                if error.code == 403:
                    fail(
                        "Not allowed to delete package versions. Give this repository the Admin role in the "
                        "package settings (Manage Actions access)."
                    )
                raise
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
