# Docker Compose

The recommended setup for a single host: one file starts Statora, PostgreSQL and Redis.

## 1. Get the files

```bash
mkdir statora && cd statora
curl -fsSLO https://raw.githubusercontent.com/timothestoifl24/statora/main/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/timothestoifl24/statora/main/.env.example -o .env
```

## 2. Configure

Edit `.env`. Three values are required:

```ini
# Long random value: signs sessions and encrypts stored identity-provider secrets.
STATORA_SECRET_KEY=          # openssl rand -hex 32
# Password for the bundled PostgreSQL container.
POSTGRES_PASSWORD=           # openssl rand -hex 16
# The address people use to reach Statora (used for SSO callback URLs).
STATORA_BASE_URL=https://status.example.com
```

To generate both secrets in one go:

```bash
sed -i.bak "s/^STATORA_SECRET_KEY=.*/STATORA_SECRET_KEY=$(openssl rand -hex 32)/; s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" .env
```

::: warning Keep STATORA_SECRET_KEY stable
Changing it signs everybody out and makes stored LDAP, OIDC and SAML secrets unreadable; you would have to re-enter them.
:::

Other settings, such as the version pin (`STATORA_VERSION`), the host port, data retention and login rate limits, are listed in the [configuration reference](/reference/configuration).

## 3. Start

```bash
docker compose up -d
docker compose ps            # app, postgres and redis should be "healthy"
```

## 4. Create the first admin

Open `http://<host>:8000/admin`. On a fresh instance there is no sign-in yet: the page asks you to create the admin account, then signs you in.

::: warning
Whoever opens the page first creates the admin, so do this right after starting Statora, before you expose it to the internet.
:::

::: tip Demo data
`docker compose exec app statora seed` adds demo monitors, a stack and a redundancy group, and a status page at `/s/demo`. Delete them whenever you like.
:::

## The compose file

```yaml
services:
  app:
    image: docker.io/timothestoifl24/statora:${STATORA_VERSION:-latest}
    restart: unless-stopped
    env_file: .env
    environment:
      STATORA_DATABASE_URL: postgresql+asyncpg://statora:${POSTGRES_PASSWORD}@postgres:5432/statora
      STATORA_REDIS_URL: redis://redis:6379/0
    ports:
      - "${STATORA_HTTP_PORT:-8000}:8000"
    sysctls:
      net.ipv4.ping_group_range: "0 2147483647"   # unprivileged ping
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  postgres:
    image: docker.io/library/postgres:18-alpine
    environment:
      POSTGRES_USER: statora
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: statora
    volumes:
      - pgdata:/var/lib/postgresql   # PostgreSQL 18+ layout

  redis:
    image: docker.io/library/redis:8.8-alpine
    command: ["redis-server", "--save", "", "--appendonly", "no"]

volumes:
  pgdata:
```

The full file in the repository also has health checks and restart policies.

## HTTPS with a reverse proxy

Statora speaks plain HTTP on port 8000. Terminate TLS in front of it and forward the usual headers. Then set `STATORA_BASE_URL=https://…` and `STATORA_SECURE_COOKIES=true` in `.env` and run `docker compose up -d` again.

::: code-group

```caddy [Caddy]
status.example.com {
    reverse_proxy localhost:8000
}
```

```nginx [nginx]
server {
    listen 443 ssl;
    server_name status.example.com;
    # ssl_certificate / ssl_certificate_key …

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```yaml [Traefik labels]
services:
  app:
    labels:
      - traefik.enable=true
      - traefik.http.routers.statora.rule=Host(`status.example.com`)
      - traefik.http.routers.statora.tls.certresolver=letsencrypt
      - traefik.http.services.statora.loadbalancer.server.port=8000
```

:::

When a proxy is in front, you can stop publishing the port to all interfaces. Set `STATORA_HTTP_PORT=127.0.0.1:8000`, or remove `ports:` and put the proxy on the same Docker network.

## Backups

Everything worth keeping is in PostgreSQL:

```bash
docker compose exec -T postgres pg_dump -U statora statora | gzip > statora-$(date +%F).sql.gz
```

Restore into a fresh stack with `gunzip -c backup.sql.gz | docker compose exec -T postgres psql -U statora statora`. Redis needs no backup.

## Podman

The same file works with `podman compose`. Rootless Podman can't publish ports below 1024, so keep 8000 and put a proxy in front.
