<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="branding/statora-logo-dark.svg">
    <img src="branding/statora-logo.svg" alt="Statora" height="72">
  </picture>
</p>

<p align="center"><strong>Self-hosted uptime monitoring and status pages.</strong><br>
Watch your services, group them the way they really depend on each other, and tell your users what's going on.</p>

<p align="center">
  <a href="https://github.com/timothestoifl24/statora/releases/latest"><img src="https://img.shields.io/github/v/release/timothestoifl24/statora?style=for-the-badge&label=version&color=1f6feb&logo=github&logoColor=white" alt="Latest release"></a>
  <a href="https://hub.docker.com/r/timothestoifl24/statora"><img src="https://img.shields.io/docker/pulls/timothestoifl24/statora?style=for-the-badge&color=12b5a0&logo=docker&logoColor=white" alt="Docker pulls"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/timothestoifl24/statora?style=for-the-badge&color=0b1f33" alt="License"></a>
</p>

<p align="center">
  🌐 <a href="https://statora.timothestoifl24.dev">Website</a> &nbsp;·&nbsp;
  📦 <a href="https://statora.timothestoifl24.dev/setup/">Installation</a> &nbsp;·&nbsp;
  📖 <a href="https://statora.timothestoifl24.dev/guide/">Guide</a> &nbsp;·&nbsp;
  🖼️ <a href="https://statora.timothestoifl24.dev/screenshots">Screenshots</a> &nbsp;·&nbsp;
  📝 <a href="CHANGELOG.md">Changelog</a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/public/screenshots/status-page-dark.webp">
    <img src="docs/public/screenshots/status-page-light.webp" alt="Statora status page" width="820">
  </picture>
</p>

> [!NOTE]
> The documentation at [statora.timothestoifl24.dev](https://statora.timothestoifl24.dev) describes the latest release. To see what's in development for the next one (the `develop` branch), visit [statora.timothestoifl24.dev/dev](https://statora.timothestoifl24.dev/dev/). The switch at the top of every page moves between the two.

## ✨ Features

| Feature | What you get |
|---|---|
| 📡 **Monitors** | HTTP(S), TCP, ping, DNS and SQL checks, with retries and a latency threshold for *degraded* |
| 🧩 **Groups** | Stack and redundancy groups that model how your services depend on each other |
| 📊 **Status pages** | As many public pages as you like, each with its own accent colour, logo and favicon |
| 🚨 **Incidents & maintenance** | Markdown timelines, impact levels, and maintenance that doesn't count as downtime |
| 🖥️ **Admin panel** | Dashboard, tile view and wallboard, latency charts and a page builder |
| 🔐 **Single sign-on** | LDAP / Active Directory, OAuth2 / OpenID Connect and SAML 2.0, with group-to-role mapping |
| 🔌 **REST API** | OpenAPI 3.1, API tokens and stable `operationId`s, ready for Terraform |
| 🐳 **One container** | A single image for web and checks, plus PostgreSQL and Redis |

<details>
<summary><b>All the details</b></summary>

- 📡 **Monitors:** HTTP(S) (status codes, keyword, headers/body, TLS verification), TCP port, ICMP ping, DNS (any record type, expected value), SQL queries against PostgreSQL, MySQL/MariaDB, SQL Server and Oracle (expected value, minimum rows). Each has an interval, a timeout, retries before going down, and a "degraded" latency threshold. A monitor can have an icon (a bundled Font Awesome icon or your own image) and a link to the app behind it.
- 🧩 **Groups:** combine monitors into one component.
  - **Stack:** every member must be healthy.
  - **Redundancy:** at least *N* members must be up, e.g. one of two nodes. While enough nodes are up, losing one shows as *degraded*.
  - Groups can contain other groups. A group re-evaluates as soon as a member changes status, and it appears on status pages, in uptime history and in the API like any other monitor.
- 📊 **Status pages:** grouped components, uptime bars (per minute, hour or day), active incidents, scheduled maintenance and past incidents. Pages are server-rendered (Jinja2 + HTMX), work without JavaScript, refresh themselves, and have a light/dark toggle that remembers each visitor's choice. Each page has its own accent colour and favicon, and the "Powered by Statora" footer can be switched off.
- 🚨 **Incidents & maintenance:** incidents have an impact level and a timeline of updates written in Markdown. Monitors inside a maintenance window show as *under maintenance*, and that time doesn't count as downtime. Incidents can carry an ITSM ticket number and link, and maintenance windows a change number and link. These are internal and never appear on the public page.
- 🖥️ **Admin panel:** built on [Tabler](https://tabler.io) with [Font Awesome](https://fontawesome.com) icons. Problems come first on the dashboard, a tile view doubles as a wallboard (`/admin?kiosk=1`), and records are created and edited in dialogs. It also covers latency charts, the status-page builder, users, authentication providers and API tokens.
- 🔐 **Authentication:**
  - local accounts,
  - **LDAP / Active Directory**,
  - **OAuth2 / OpenID Connect** (Keycloak, Entra ID, Google, GitHub, Authentik…),
  - **SAML 2.0**.
  - Users can be created automatically on first login, and groups map to roles (`admin`, `editor`, `viewer`).
- 🔌 **REST API:** OpenAPI 3.1 with Swagger UI at `/api/docs` and ReDoc at `/api/redoc`. It uses API tokens and has stable `operationId`s, so it is ready for a Terraform provider.
- 🛡️ **Secure by default:** a strict Content-Security-Policy without inline scripts, uploaded images rebuilt before they're stored, and secrets encrypted in the database.

</details>

### 🧱 Stack

- 🐍 Python 3.13+ (the container image runs 3.15), FastAPI and SQLAlchemy 2 (async)
- 🐘 PostgreSQL for storage, 🟥 Redis for caching and coordination (tested with PostgreSQL 18 and Redis 8.8)
- 🐳 One container image for the app

## 🖼️ Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/public/screenshots/dashboard.webp" alt="Monitor dashboard"><p align="center"><sub>Dashboard: problems first</sub></p></td>
    <td width="50%"><img src="docs/public/screenshots/dashboard-tiles.webp" alt="Tile view"><p align="center"><sub>Tile view and wallboard</sub></p></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/public/screenshots/monitor-detail.webp" alt="Monitor detail"><p align="center"><sub>Latency and uptime per monitor</sub></p></td>
    <td width="50%"><img src="docs/public/screenshots/page-builder.webp" alt="Status page builder"><p align="center"><sub>Status page builder</sub></p></td>
  </tr>
</table>

More on the [screenshots page](https://statora.timothestoifl24.dev/screenshots).

## 🚀 Installation

Statora is one container image, `docker.io/timothestoifl24/statora`, plus PostgreSQL and Redis.

| Image tag | Channel |
|---|---|
| `1.1.1`, `1.1`, `1`, `latest` | ✅ **Stable** releases from `main`, for production |
| `1.2.0-beta.N`, `beta` | 🧪 **Beta** builds from `develop`, previews of the next release |

See [container images](https://statora.timothestoifl24.dev/reference/images) for details. The quickest start uses Docker Compose:

```bash
curl -fsSLO https://raw.githubusercontent.com/timothestoifl24/statora/main/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/timothestoifl24/statora/main/.env.example -o .env
# set STATORA_SECRET_KEY, POSTGRES_PASSWORD and STATORA_BASE_URL in .env
docker compose up -d
# open http://localhost:8000 and create the admin account
```

Step-by-step guides:

- 🐙 [Docker Compose](https://statora.timothestoifl24.dev/setup/docker-compose): recommended for a single host, including HTTPS behind Caddy, nginx or Traefik, and backups.
- 🐳 [Docker](https://statora.timothestoifl24.dev/setup/docker): plain `docker run`, or an existing PostgreSQL.
- ☸️ [Kubernetes](https://statora.timothestoifl24.dev/setup/kubernetes): Kustomize manifests in [`deploy/kubernetes`](deploy/kubernetes).

## 🏭 Production

The app ships as **one container image**. PostgreSQL and Redis run as separate containers. The full configuration reference is at [statora.timothestoifl24.dev/reference/configuration](https://statora.timothestoifl24.dev/reference/configuration).

- 🔒 **HTTPS:** put a TLS-terminating reverse proxy in front of the app and set `STATORA_SECURE_COOKIES=true`. The app trusts `X-Forwarded-*` headers.
- 📶 **Ping** needs unprivileged ICMP. `docker-compose.yml` sets `net.ipv4.ping_group_range`. If your platform forbids that sysctl, add `cap_add: [NET_RAW]` instead.
- 📈 **Scaling:** every replica serves the web UI and API. A Redis leader lock makes sure only one replica runs checks at a time. To split the roles, use `STATORA_ROLE=web` or `STATORA_ROLE=worker`; the same image does both.
- 🗄️ **Data retention:** raw heartbeats are kept for `STATORA_HEARTBEAT_RETENTION_DAYS` (default 30). Daily rollups for the daily uptime bars are kept indefinitely; minute and hour bars use the raw heartbeats.

### ⚙️ Configuration

All settings are environment variables with the `STATORA_` prefix (see [.env.example](.env.example)):

| Variable | Default | |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://statora:statora@localhost:5432/statora` | |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `SECRET_KEY` | — (**required**) | Signs sessions and encrypts stored IdP secrets |
| `BASE_URL` | `http://localhost:8000` | Public URL; used for OIDC/SAML callbacks |
| `ROLE` | `all` | `all`, `web` or `worker` |
| `SECURE_COOKIES` | `false` | Set `true` behind HTTPS |
| `DISABLE_LOCAL_LOGIN` | `false` | Hide local login for everyone except local admins |
| `HEARTBEAT_RETENTION_DAYS` | `30` | |
| `PAGE_CACHE_TTL` | `30` | Seconds a status page stays cached in Redis |
| `LOGIN_RATE_LIMIT` / `LOGIN_RATE_WINDOW` | `10` / `300` | Login attempts per IP and per username |

## 🔐 Authentication providers

Configure providers under **Admin → Authentication**, or through `/api/v1/auth-providers`.

| Type | What you enter | What the IdP needs |
|---|---|---|
| 📇 LDAP / AD | Server URI, then either a service account + search base + filter, or a direct-bind DN template. Group lookup via `memberOf` or a group search | — |
| 🔑 OAuth2 / OIDC | Discovery URL (or explicit endpoints for plain OAuth2), client ID/secret, claim names (supports nested ones such as `realm_access.roles`) | Redirect URL `BASE_URL/auth/oidc/<id>/callback` |
| 🎫 SAML 2.0 | IdP metadata URL or XML (or entity ID + SSO URL + certificate), attribute names | ACS `BASE_URL/auth/saml/<id>/acs`, SP metadata at `BASE_URL/auth/saml/<id>/metadata` |

How it works:
- Secrets are encrypted in the database with a key derived from `STATORA_SECRET_KEY`. The UI and API never return them.
- **Test connection** checks the LDAP bind, OIDC discovery or SAML metadata.
- Group mapping is a list of `group = role` lines. The highest matching role wins, and roles are refreshed at every login.
- Local admins can always sign in, so a broken IdP can't lock you out.

## 🔌 REST API

All endpoints live under `/api/v1`. Send a token as `Authorization: Bearer st_…`.

There are two ways to get a token:
- **In the UI:** Profile → API tokens. The token is shown once. Scopes are `read` and `write`, and expiry is optional.
- **With credentials:** for local and LDAP accounts:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "…", "name": "terraform", "scopes": ["read", "write"]}'
```

Example call:

```bash
curl -X POST http://localhost:8000/api/v1/monitors \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name": "Website", "type": "http", "target": "https://example.com", "interval_s": 60,
       "config": {"expected_status": ["200-299"], "keyword": "Welcome"}}'
```

Resources:
- `monitors` (+ `/heartbeats`, `/uptime`)
- `status-pages` (nested groups and items)
- `incidents` (+ `/updates`)
- `maintenances`
- `media` (image uploads for icons and favicons)
- `users`
- `auth-providers` (+ `/test`)
- `tokens`
- `me`
- Public, no auth: `GET /api/v1/public/pages/{slug}/summary`

What the API does:
- **Permissions:** a token can never do more than its user's role allows.
- **Errors:** always shaped as `{"detail": …, "code": "<machine-readable>"}`.
- **CRUD:** every resource has list (paginated and filterable), get, create, `PATCH`, `PUT` where it makes sense, and an idempotent `DELETE`.

This is the surface a Terraform provider (e.g. built with `terraform-plugin-framework`) would wrap.

## 🛠️ Development

You need Python 3.13+, [uv](https://docs.astral.sh/uv/), and Docker or Podman for PostgreSQL and Redis. On Python 3.15, SAML's `xmlsec` is compiled from source; see [development](https://statora.timothestoifl24.dev/reference/development).

```bash
docker compose -f docker-compose.dev.yml up -d      # PostgreSQL :5432, Redis :6379
uv sync --all-extras
uv run statora init --seed                       # migrate, demo data
uv run statora dev                               # http://localhost:8000
```

- 🖥️ Admin panel: <http://localhost:8000/admin> (the first visit asks you to create the admin account)
- 📊 Demo status page: <http://localhost:8000/s/demo> (also served at `/`)
- 📚 API docs: <http://localhost:8000/api/docs>

`init --seed` creates six demo monitors, including one that is broken on purpose and goes down after its retries. It also creates a demo page with a resolved incident and an upcoming maintenance window.

### ⌨️ CLI

| Command | What it does |
|---|---|
| `statora init [--seed/--no-seed]` | Migrate, optionally add demo data |
| `statora dev [--host] [--port]` | Web + checker with auto-reload |
| `statora serve [--no-migrate]` | Production entrypoint (migrates first by default) |
| `statora migrate` | Apply database migrations |
| `statora reset-admin [--username]` | Reset the initial admin's password and re-enable it |
| `statora seed` | Add the demo data |

### 🧪 Tests

```bash
uv run pytest            # uses the dev compose services (database statora_test, Redis DB 15)
uv run ruff check src tests && uv run ruff format src tests
```

- **Unit tests** need no services.
- **Integration tests** skip themselves when PostgreSQL/Redis aren't reachable. Point them elsewhere with `STATORA_TEST_DATABASE_URL` / `STATORA_TEST_REDIS_URL`.
- **LDAP tests** need the OpenLDAP container: `docker compose -f docker-compose.dev.yml --profile sso up -d openldap`. The same profile also starts Keycloak on :8080 for trying OIDC/SAML by hand.

New migration after changing models:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

### 📁 Layout

```
src/statora/
  checks/        HTTP, TCP, ping, DNS, SQL checks → CheckResult
  scheduler.py   per-monitor asyncio loops, Redis leader lock, periodic resync
  services/      state machine + daily rollups, status page summary, shared CRUD, media
  auth/          passwords, API tokens, rate limiting, LDAP/OIDC/SAML providers, provisioning
  web/           admin (Tabler), public pages, login/SSO routes, /api/v1
  templates/     Jinja2 templates; static/ holds vendored Tabler, Font Awesome, htmx, ApexCharts, Swagger UI
  static/brand/  logo, favicons, app icons, web manifest (generated from branding/)
  migrations/    Alembic
branding/        brand kit: logo/icon SVG sources, PNG/ICO exports, generator script
deploy/          Kubernetes (Kustomize) manifests
docs/            website and documentation (VitePress): main at statora.timothestoifl24.dev, develop at /dev
.github/         CI, container image and GitHub Pages workflows
```

## 🎨 Brand

The logo, icon and colour palette are documented in [branding/README.md](branding/README.md).

## 🤝 Contributing

Contributions are welcome. Pull requests go to the `develop` branch; `main` is production. Please read and accept [CONTRIBUTING.md](CONTRIBUTING.md) before opening one, and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## 🛡️ Security

Please report vulnerabilities privately through [GitHub's private vulnerability reporting](https://github.com/timothestoifl24/statora/security/advisories/new). You can also email [security@timothestoifl24.dev](mailto:security@timothestoifl24.dev). See [SECURITY.md](SECURITY.md) for supported versions, response times and scope.

## 📄 License

Statora is released under the [MIT License](LICENSE). Third-party components and their licenses are listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
