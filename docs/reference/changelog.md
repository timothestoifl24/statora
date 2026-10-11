# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/).

::: info How this changelog works
Changes collect under the upcoming version while it's being developed; you can try them with the [`beta` image](./images#beta-preview-of-the-next-release). The date is set when the version is released.
:::

## 0.1.0 — unreleased

First public release.

- **Monitors:** HTTP(S), TCP, ping and DNS checks with retries and latency thresholds.
- **Groups:** stack and redundancy groups, nesting, instant re-evaluation when a member changes, and expandable members on status pages.
- **Status pages:** 90-day uptime bars, incidents, maintenance, light/dark toggle, accent colours and an optional "Powered by" footer.
- **Incidents and maintenance:** Markdown timelines, and internal ITSM ticket and change references.
- **Sign-in:** local accounts, LDAP / Active Directory, OAuth2 / OpenID Connect and SAML 2.0, with just-in-time provisioning and group-to-role mapping.
- **REST API:** OpenAPI 3.1, Swagger UI and scoped API tokens.
- **Platform:** Python 3.15 container image; tested on Python 3.12–3.15, PostgreSQL 18 and Redis 8.8.
- **Deployment:** single container image, Docker Compose and Kubernetes manifests, horizontal scaling with a scheduler leader lock, and serialized migrations.
