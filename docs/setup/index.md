# Setup

Statora is one container image, `docker.io/timothestoifl24/statora`, plus a PostgreSQL database and a Redis instance. How you run those three is up to you:

| Method | Good for | Guide |
|---|---|---|
| **Docker / Podman** | Most installations: one host, with Compose or plain `docker run` | [Docker / Podman](./docker) |
| **Kubernetes** | Clusters; several replicas behind an Ingress | [Kubernetes](./kubernetes) |

<span id="what-happens-on-first-start"></span>Once it runs, the [initial setup](./initial-setup) walks you through the admin account, HTTPS, the first monitors and a status page.

## Requirements

- **Container runtime:** Docker 24+ or Podman 4+ (with Compose for the Compose setup), or Kubernetes 1.27+.
- **PostgreSQL 14 or newer.** The examples and CI use PostgreSQL 18.
- **Redis 6 or newer.** The examples and CI use Redis 8.8. Redis only holds caches, locks and short-lived state, so it doesn't need persistence or backups.
- **Resources:** about 200 MB of RAM for the app. A few hundred monitors fit comfortably on one small VM.
- **Network:** outbound access to whatever you monitor. Ping checks need unprivileged ICMP; each guide shows how to allow it.

## Afterwards <span id="after-installing"></span>

- [Advanced config](./advanced-config): every environment variable, the command line and the health endpoint.
- [Upgrading](./upgrading): image tags, release channels, version pinning and rollbacks.
- [REST API](./api): manage Statora from scripts, with the OpenAPI spec to import into your API client.
