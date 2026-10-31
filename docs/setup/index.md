# Choose a setup method

Statora is one container image, `docker.io/timothestoifl24/statora`, plus a PostgreSQL database and a Redis instance. How you run those three is up to you:

| Method | Good for | Guide |
|---|---|---|
| **Docker Compose** | Most installations: one host, everything in one file | [Docker Compose](./docker-compose) |
| **Docker** | Hosts where you manage containers by hand, or already have PostgreSQL | [Docker](./docker) |
| **Kubernetes** | Clusters; several replicas behind an Ingress | [Kubernetes](./kubernetes) |

## Requirements

- **Container runtime:** Docker 24+ or Podman 4+ (with the Compose plugin for the Compose setup), or Kubernetes 1.27+.
- **PostgreSQL 14 or newer.** The examples and CI use PostgreSQL 18.
- **Redis 6 or newer.** The examples and CI use Redis 8.8. Redis only holds caches, locks and short-lived state, so it doesn't need persistence or backups.
- **Resources:** about 200 MB of RAM for the app. A few hundred monitors fit comfortably on one small VM.
- **Network:** outbound access to whatever you monitor. Ping checks need unprivileged ICMP; each guide shows how to allow it.

## What happens on first start

1. The app applies its database migrations. They are serialized, so several replicas can start at once.
2. One replica becomes the scheduler leader and starts checking monitors.
3. The web UI comes up on port `8000`.

Then create the first admin:

```bash
statora create-admin          # inside the container, see your guide for the exact command
```

## After installing

- Put Statora behind HTTPS and set `STATORA_SECURE_COOKIES=true` and `STATORA_BASE_URL`; see [configuration](/reference/configuration).
- Add [monitors](/guide/monitors), build a [status page](/guide/status-pages), and invite your team or connect [LDAP, OIDC or SAML](/guide/authentication).
- Create an [API token](/guide/api) if you want to manage Statora from scripts or Terraform.
