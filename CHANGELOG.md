# Changelog

All notable changes to Statora are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Statora follows [Semantic Versioning](https://semver.org/).

Changes collect under the upcoming version while it's being developed, and you can try them with the [`beta` image](https://statora.stoifl.app/reference/images#beta-preview-of-the-next-release). The date is set when the version is released. Each section also appears in the matching [GitHub release](https://github.com/timothestoifl24/statora/releases).

## [0.1.0] - Unreleased

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

[0.1.0]: https://github.com/timothestoifl24/statora/releases/tag/v0.1.0
