# Container images

Images are published to the GitHub Container Registry for `linux/amd64` and `linux/arm64`:

```
ghcr.io/timothestoifl24/statora
```

| Tag | Updated | Use |
|---|---|---|
| `0.1.0`, `0.1` | on each release | **Production**: pin a full version, or a minor version to get patch updates. |
| `latest` | on every push to `main` (production) | Quick starts, and following production without pinning. |
| `edge` | on every push to `develop` | Testing changes before they reach production. |
| `sha-<commit>` | on every build | Reproducing a specific build. |

Each image comes with build provenance and an SBOM attestation. Verify an image with the GitHub CLI:

```bash
gh attestation verify oci://ghcr.io/timothestoifl24/statora:0.1.0 --owner timothestoifl24
```

## What's inside

- Debian trixie (slim) with Python 3.15.0, from uv's standalone CPython builds. The app lives in a virtual environment at `/app/.venv`.
- Runs as UID 10001, listens on port 8000, and the default command is `statora serve`.
- No compilers or build tools in the final image. SAML support (`xmlsec`) is included.
