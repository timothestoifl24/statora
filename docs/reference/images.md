# Container images

Images are published to the GitHub Container Registry for `linux/amd64` and `linux/arm64`:

```
ghcr.io/timothestoifl24/statora
```

There are two release channels.

## Stable: for production

Built from the `main` branch. Every release has a version number, a git tag (`v0.2.0`) and a [GitHub release](https://github.com/timothestoifl24/statora/releases).

| Tag | Points to | Use it when |
|---|---|---|
| `0.2.0` | exactly that release, never changes | **Production.** You decide when to upgrade. |
| `0.2` | the newest `0.2.x` release | You want bug fixes automatically, but no new features. |
| `latest` | the newest stable release | Quick starts and trying Statora out. |

From version 1.0 on, a major-version tag such as `1` is published as well.

## Beta: preview of the next release

Built from the `develop` branch on every change, so it contains the newest features before they're released. Each beta is a [pre-release on GitHub](https://github.com/timothestoifl24/statora/releases).

| Tag | Points to | Use it when |
|---|---|---|
| `0.3.0-beta.4` | exactly that beta, never changes | Testing a specific build, or reporting a bug against it. |
| `beta` | the newest beta | Following development on a test instance. |

::: warning Betas are not for production
They're tested by CI like every release, but they can contain unfinished features and database migrations that the stable release doesn't have yet. Run them against a copy of your data, and see [Trying a beta](./upgrading#trying-a-beta) before you switch an instance back to stable.
:::

## Other tags

`sha-<commit>` tags point to the image built from a specific commit, on either branch. They're useful for pinning exactly what you tested.

## How versions work

- **Version numbers** follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
- **Beta numbering:** betas carry the number of the release they lead up to, so `0.3.0-beta.4` is the fourth preview of 0.3.0, and sorts *before* `0.3.0`.
- **Releases are automatic:** a stable release is created when a new version is merged into `main`, and a beta for every change merged into `develop`.
- **Checking a running instance:** the version is shown in the admin panel footer and in the API (`GET /api/openapi.json`, `info.version`).

## Verifying an image

Each image has an SBOM and a build provenance attestation. Verify with the GitHub CLI:

```bash
gh attestation verify oci://ghcr.io/timothestoifl24/statora:0.2.0 --owner timothestoifl24
```

## What's inside

- Debian trixie (slim) with Python 3.15.0, from uv's standalone CPython builds. The app lives in a virtual environment at `/app/.venv`.
- Runs as UID 10001, listens on port 8000, and the default command is `statora serve`.
- No compilers or build tools in the final image. SAML support (`xmlsec`) is included.
