"""Small GitHub and GHCR API helpers shared by the image cleanup scripts.

Deleting an image means deleting its package version (the image index) together with what hangs
off it: the untagged platform images and attestation manifests it points to, and attestations
pushed next to it as sha256-<digest> tags, unless an image that stays still uses them.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
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
    data: dict | None = None,
):
    auth = f"Basic {token}" if basic else f"Bearer {token}"
    headers = {"Authorization": auth, "Accept": accept}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, headers=headers, data=body)
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


def package_versions(owner: str, package: str, token: str) -> tuple[str, list[dict]]:
    """API URL of the container package's versions, and all of its versions."""
    kind = "orgs" if request(f"{API}/users/{owner}", token)[0]["type"] == "Organization" else "users"
    base = f"{API}/{kind}/{owner}/packages/container/{package}/versions"
    return base, paginate(base, token)


def tags(version: dict) -> list[str]:
    return version["metadata"]["container"]["tags"]


def with_orphans(doomed: dict[int, dict], versions: list[dict], owner: str, package: str, token: str) -> None:
    """Add to doomed (by version id) what only the doomed images use."""
    # Attestations pushed next to an image are tagged sha256-<digest of that image>.
    doomed_digests = {v["name"] for v in doomed.values()}
    for version in versions:
        if any(t.split(".")[0].replace("sha256-", "sha256:") in doomed_digests for t in tags(version)):
            doomed.setdefault(version["id"], version)

    # Untagged platform images and attestation manifests behind the deleted indexes, unless a
    # kept tagged version still points to them.
    if not doomed:
        return
    registry = registry_token(owner, package, token)
    orphans: set[str] = set()
    for version in doomed.values():
        orphans |= children(owner, package, version["name"], registry)
    for version in versions:
        if version["id"] not in doomed and tags(version):
            orphans -= children(owner, package, version["name"], registry)
    for version in versions:
        if version["name"] in orphans and not tags(version):
            doomed.setdefault(version["id"], version)


def delete_versions(base: str, doomed: dict[int, dict], token: str, dry_run: bool) -> list[str]:
    """Delete the doomed versions, oldest first. Returns one Markdown list entry per version."""
    entries = []
    for version in sorted(doomed.values(), key=lambda v: v["created_at"]):
        entries.append(f"- `{version['name'][:19]}` {', '.join(tags(version)) or 'untagged'}")
        if dry_run:
            continue
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
    return entries


def report(title: str, entries: list[str]) -> None:
    """Print a Markdown section and add it to the job summary."""
    lines = [f"### {title}", "", *(entries or ["_Nothing to delete._"]), ""]
    print("\n".join(lines))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as fh:
            fh.write("\n".join(lines) + "\n")
