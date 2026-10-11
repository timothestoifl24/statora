"""Decide what the container image workflow publishes for the current event.

- main (production): a new version in pyproject.toml becomes release vX.Y.Z with the image
  tags X.Y.Z, X.Y, latest (and X from 1.0 on). If vX.Y.Z already exists, nothing is published.
- develop (pre-release): every push becomes vX.Y.Z-beta.N with the image tags X.Y.Z-beta.N and
  beta. Fails if vX.Y.Z is already released, because develop must hold the next version.
- anything else (pull requests, other branches): build and test only.

Reads GITHUB_EVENT_NAME, GITHUB_REF, GITHUB_SHA and IMAGE; writes key=value pairs to
GITHUB_OUTPUT (or stdout). Run from the repository root with tags fetched.
"""

import os
import re
import subprocess
import sys
import tomllib

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def tags() -> set[str]:
    out = subprocess.run(["git", "tag", "--list", "v*"], capture_output=True, text=True, check=True).stdout
    return set(out.split())


def fail(message: str) -> None:
    print(f"::error::{message}")
    sys.exit(1)


def main() -> None:
    version = tomllib.load(open("pyproject.toml", "rb"))["project"]["version"]
    match = SEMVER.match(version)
    if not match:
        fail(f"project.version {version!r} in pyproject.toml must be a plain X.Y.Z version")
    major, minor, _ = (int(part) for part in match.groups())

    event = os.environ.get("GITHUB_EVENT_NAME", "")
    ref = os.environ.get("GITHUB_REF", "")
    sha = os.environ.get("GITHUB_SHA", "0000000")[:7]
    image = os.environ.get("IMAGE", "ghcr.io/example/statora")
    existing = tags()

    result = {"channel": "none", "publish": "false", "version": f"{version}-dev", "tag": "", "image_tags": ""}

    if event in ("push", "workflow_dispatch") and ref == "refs/heads/main":
        tag = f"v{version}"
        if tag in existing:
            print(f"::notice::{tag} is already released; nothing to publish. Bump the version to release.")
            result["version"] = version
        else:
            names = [version, f"{major}.{minor}", "latest", f"sha-{sha}"]
            if major >= 1:
                names.insert(2, str(major))
            result.update(channel="stable", publish="true", version=version, tag=tag, image_tags=names)

    elif event in ("push", "workflow_dispatch") and ref == "refs/heads/develop":
        if f"v{version}" in existing:
            fail(
                f"v{version} is already released. Bump project.version in pyproject.toml on develop "
                "to the next version, so betas are labelled for the upcoming release."
            )
        numbers = [
            int(m.group(1)) for t in existing if (m := re.fullmatch(rf"v{re.escape(version)}-beta\.(\d+)", t))
        ]
        beta = f"{version}-beta.{max(numbers, default=0) + 1}"
        result.update(
            channel="beta", publish="true", version=beta, tag=f"v{beta}", image_tags=[beta, "beta", f"sha-{sha}"]
        )

    if isinstance(result["image_tags"], list):
        result["image_tags"] = " ".join(f"{image}:{name}" for name in result["image_tags"])

    lines = [f"{key}={value}" for key, value in result.items()]
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
