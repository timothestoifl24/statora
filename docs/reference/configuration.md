# Configuration

Statora is configured with environment variables, all prefixed with `STATORA_`. When you run it outside a container, it also reads a `.env` file from the working directory.

## Settings

| Variable | Default | Description |
|---|---|---|
| `STATORA_DATABASE_URL` | `postgresql+asyncpg://statora:statora@localhost:5432/statora` | PostgreSQL connection. Keep the `+asyncpg` driver part. |
| `STATORA_REDIS_URL` | `redis://localhost:6379/0` | Redis connection. |
| `STATORA_SECRET_KEY` | — | **Required.** Signs sessions and encrypts identity-provider secrets. Use a long random value and keep it stable. |
| `STATORA_BASE_URL` | `http://localhost:8000` | Public URL, used to build OIDC and SAML callback URLs. |
| `STATORA_SECURE_COOKIES` | `false` | Mark the session cookie `Secure`. Turn on behind HTTPS. |
| `STATORA_ROLE` | `all` | `all`, `web` (UI + API only) or `worker` (checks only). The same image does all three. |
| `STATORA_HOST` / `STATORA_PORT` | `0.0.0.0` / `8000` | Listen address. |
| `STATORA_HEARTBEAT_RETENTION_DAYS` | `30` | How long raw check results are kept. Daily rollups (the 90-day bars) are kept indefinitely. |
| `STATORA_PAGE_CACHE_TTL` | `30` | Seconds a status page summary stays cached. Changes clear it immediately. |
| `STATORA_SESSION_MAX_AGE` | `43200` | Admin session lifetime in seconds (12 h). |
| `STATORA_DISABLE_LOCAL_LOGIN` | `false` | Hide password login for everyone except local admins, for SSO-only setups. |
| `STATORA_LOGIN_RATE_LIMIT` | `10` | Login attempts allowed per IP address and per username… |
| `STATORA_LOGIN_RATE_WINDOW` | `300` | …within this many seconds. |
| `FORWARDED_ALLOW_IPS` | `*` in the image | Proxies whose `X-Forwarded-*` headers are trusted. |

Compose-only variables, read by `docker-compose.yml` and not by the app:

| Variable | Default | |
|---|---|---|
| `POSTGRES_PASSWORD` | — | Password for the bundled PostgreSQL. |
| `STATORA_VERSION` | `latest` | Image tag to run. |
| `STATORA_HTTP_PORT` | `8000` | Published port, for example `127.0.0.1:8000`. |

## Command line

The `statora` command is available inside the container:

| Command | |
|---|---|
| `statora serve [--no-migrate]` | Start the server; this is the container's default command. |
| `statora migrate` | Apply database migrations. |
| `statora create-admin` | Create a local admin, or reset its password. |
| `statora seed` | Add demo monitors, groups and a status page at `/s/demo`. |
| `statora init [--seed]` | Migrate, create an admin and optionally add demo data, in one step. |
| `statora dev` | Development server with auto-reload. |

## Health endpoint

`GET /healthz` returns `200` with `{"status":"ok","database":"ok","redis":"ok","scheduler":"leader|standby|off"}`, or `503` if PostgreSQL or Redis can't be reached.
