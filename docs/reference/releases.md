---
title: Releases
description: Release channels and container image tags - which tag to run in production, how betas work, and where to find every release.
---

# Releases

Every release is published as a container image on [Docker Hub](https://hub.docker.com/r/timothestoifl24/statora), for `linux/amd64` and `linux/arm64`:

```
docker.io/timothestoifl24/statora
```

What changed in each version is in the [changelog](./changelog), and every release also has a page under [GitHub Releases](https://github.com/timothestoifl24/statora/releases) with its notes and the pull requests that went into it.

::: info Moved from GitHub Container Registry
Up to version 1.1.1, images were published as `ghcr.io/timothestoifl24/statora`. Those releases are on Docker Hub as well, under the same tags, and new images are only published to Docker Hub, so switch the image name in your setup.
:::

There are two release channels.

## Stable: for production

Built from the `main` branch. Every release has a version number (`MAJOR.MINOR.PATCH`), a git tag (`v1.1.1`) and a GitHub release.

| Tag | Points to | Use it when |
|---|---|---|
| `1.1.1` | exactly that release, never changes | **Production.** You decide when to upgrade. |
| `1.1` | the newest `1.1.x` release | You want bug fixes automatically, but no new features. |
| `1` | the newest `1.x` release | You want new features too, but no breaking changes. |
| `latest` | the newest stable release | Quick starts and trying Statora out. |

Before moving to a new minor or major version, read [upgrading](/setup/upgrading).

## Beta: preview of the next release

Built from the `develop` branch on every change to the application, so it has the newest features before they're released. A change that only touches the documentation publishes no beta. Each beta is a [pre-release on GitHub](https://github.com/timothestoifl24/statora/releases).

| Tag | Points to | Use it when |
|---|---|---|
| `1.2.0-beta.4` | exactly that beta, never changes | Testing a specific build, or reporting a bug against it. |
| `beta` | the newest beta | Following development on a test instance. |

::: warning Betas are not for production
They're tested by CI like every release, but they can contain unfinished features and database migrations that the stable release doesn't have yet. Run them against a copy of your data, and see [trying a beta](/setup/upgrading#trying-a-beta) before you switch an instance back to stable.
:::

The documentation for `develop` is published alongside them, at [/dev/](https://statora.timothestoifl24.dev/dev/).

## Pull request images

A pull request into `develop` from a branch of this repository gets its own image, `develop-pr-N` (N is the pull request number), so a change can be tried before it's merged. A comment on the pull request shows how to pull it. The image is replaced on every push and deleted when the pull request is merged or closed.

No image is built for pull requests from forks or Dependabot, or for pull requests that only change documentation; if there is no comment, there is no image to pull.

## Other tags

`sha-<commit>` tags point to the image built from a specific commit, on either branch. They're useful for pinning exactly what you tested.

## How versions work

- **Version numbers** follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
- **Beta numbering:** betas carry the number of the release they lead up to, so `1.2.0-beta.4` is the fourth preview of 1.2.0, and sorts *before* `1.2.0`.
- **Releases are automatic:** a stable release is created when a new version is merged into `main`, and a beta for every change merged into `develop`.
- **Checking a running instance:** the version is shown in the admin panel footer and in the API (`GET /api/openapi.json`, `info.version`).

## Verifying an image

Each image has an SBOM and a build provenance attestation. Verify with the GitHub CLI:

```bash
gh attestation verify oci://docker.io/timothestoifl24/statora:1.1.1 --owner timothestoifl24
```

## What's inside

- Debian trixie (slim) with Python 3.15.0, from uv's standalone CPython builds. The app lives in a virtual environment at `/app/.venv`.
- Runs as UID 10001, listens on port 8000, and the default command is `statora serve`.
- No compilers or build tools in the final image. SAML support (`xmlsec`) is included.
