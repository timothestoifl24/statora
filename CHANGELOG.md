# Changelog

All notable changes to Statora are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Statora follows [Semantic Versioning](https://semver.org/).

Changes collect under the upcoming version while it's being developed, and you can try them with the [`beta` image](https://statora.stoifl.app/reference/images#beta-preview-of-the-next-release). The date is set when the version is released. Each section also appears in the matching [GitHub release](https://github.com/timothestoifl24/statora/releases).

## [1.0.1] - Unreleased

### Changed

- **Dependencies:** updated FastAPI, Pydantic, pydantic-settings, Markdown and fakeredis to their latest patch and minor releases.

## [1.0.0] - 2026-10-11

First stable release.

### Changed

- **Releases:** a stable release deletes the betas it supersedes, so the `X.Y.Z-beta.N` images, pre-releases and tags up to that version disappear once `X.Y.Z` is out. Pin a stable tag, or follow `beta`, rather than a specific beta.

### Security

- **Redirects:** sign-in return targets (the login `next` parameter, OIDC and SAML) and admin redirects only accept paths on the same site. Previously a target such as `/\t/evil.example` could send users to another host after signing in.
- **SAML:** when the service-provider metadata can't be generated, the reason is logged instead of returned in the response, so key and certificate details are no longer exposed.

## [0.1.0] - 2026-10-11

First public release.

### Added

- **Monitors:** HTTP(S), TCP, ping and DNS checks with retries and latency thresholds.
- **Groups:** stack and redundancy groups, nesting, instant re-evaluation when a member changes, and expandable members on status pages.
- **Status pages:** 90-day uptime bars, incidents, maintenance, light/dark toggle, accent colours and an optional "Powered by" footer.
- **Incidents and maintenance:** Markdown timelines, and internal ITSM ticket and change references.
- **Sign-in:** local accounts, LDAP / Active Directory, OAuth2 / OpenID Connect and SAML 2.0, with just-in-time provisioning and group-to-role mapping.
- **REST API:** OpenAPI 3.1, Swagger UI and scoped API tokens.
- **Platform:** Python 3.15 container image; tested on Python 3.12–3.15, PostgreSQL 18 and Redis 8.8.
- **Deployment:** single container image, Docker Compose and Kubernetes manifests, horizontal scaling with a scheduler leader lock, and serialized migrations.
- **Releases:** stable images (`X.Y.Z`, `X.Y`, `latest`) from `main`, beta images (`X.Y.Z-beta.N`, `beta`) from `develop`, and GitHub releases whose notes come from this changelog.

[1.0.1]: https://github.com/timothestoifl24/statora/releases/tag/v1.0.1
[1.0.0]: https://github.com/timothestoifl24/statora/releases/tag/v1.0.0
[0.1.0]: https://github.com/timothestoifl24/statora/releases/tag/v0.1.0
