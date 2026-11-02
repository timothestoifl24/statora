# Docker / Podman

Statora runs as one container, `docker.io/timothestoifl24/statora`, next to PostgreSQL and Redis. Every command on this page works with Podman too: replace `docker` with `podman` (and `docker compose` with `podman compose`).

- **[Compose](#compose)** is the recommended setup for a single host: one file starts all three containers.
- **[Without Compose](#without-compose)** runs them one by one, for example with your own tooling or an existing PostgreSQL.

## Compose

### 1. Get the files

```bash
mkdir statora && cd statora
curl -fsSLO https://raw.githubusercontent.com/timothestoifl24/statora/main/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/timothestoifl24/statora/main/.env.example -o .env
```

### 2. Configure

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

Other settings, such as the version pin (`STATORA_VERSION`), the host port, data retention and login rate limits, are listed under [advanced config](./advanced-config).

### 3. Start

::: code-group

```bash [Docker]
docker compose up -d
docker compose ps            # app, postgres and redis should be "healthy"
```

```bash [Podman]
podman compose up -d
podman compose ps
```

:::

<span id="_4-create-the-first-admin"></span>Then continue with the [initial setup](./initial-setup): the first visit creates the admin account.

### The compose file

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

## Without Compose

### 1. Network and secrets

```bash
docker network create statora

export POSTGRES_PASSWORD=$(openssl rand -hex 16)
export STATORA_SECRET_KEY=$(openssl rand -hex 32)
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"   # store both somewhere safe
echo "STATORA_SECRET_KEY=$STATORA_SECRET_KEY"
```

### 2. PostgreSQL and Redis

```bash
docker run -d --name statora-postgres --network statora --restart unless-stopped \
  -e POSTGRES_USER=statora -e POSTGRES_DB=statora -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -v statora-pgdata:/var/lib/postgresql \
  docker.io/library/postgres:18-alpine

docker run -d --name statora-redis --network statora --restart unless-stopped \
  docker.io/library/redis:8.8-alpine redis-server --save "" --appendonly no
```

::: tip Using an existing PostgreSQL
Create a database and a user that owns it, then point `STATORA_DATABASE_URL` at it in the next step. Statora creates and migrates its tables itself.
:::

### 3. Statora

```bash
docker run -d --name statora --network statora --restart unless-stopped \
  -p 8000:8000 \
  --sysctl net.ipv4.ping_group_range="0 2147483647" \
  -e STATORA_DATABASE_URL="postgresql+asyncpg://statora:${POSTGRES_PASSWORD}@statora-postgres:5432/statora" \
  -e STATORA_REDIS_URL="redis://statora-redis:6379/0" \
  -e STATORA_SECRET_KEY="$STATORA_SECRET_KEY" \
  -e STATORA_BASE_URL="http://localhost:8000" \
  docker.io/timothestoifl24/statora:latest
```

The container applies database migrations on start, then serves on port 8000. Check that it's healthy:

```bash
curl -s http://localhost:8000/healthz
# {"status":"ok","database":"ok","redis":"ok","scheduler":"leader"}
```

<span id="_4-first-admin"></span>Then continue with the [initial setup](./initial-setup).

## HTTPS with a reverse proxy

Statora speaks plain HTTP on port 8000. Terminate TLS in front of it and forward the usual headers. Then set `STATORA_BASE_URL=https://…` and `STATORA_SECURE_COOKIES=true` and recreate the container (`docker compose up -d`).

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

When a proxy is in front, you can stop publishing the port to all interfaces. Set `STATORA_HTTP_PORT=127.0.0.1:8000`, or remove `ports:` and put the proxy on the same network.

## Podman notes <span id="podman"></span>

- **Compose:** `podman compose` uses `podman-compose` or the Docker Compose plugin, whichever is installed. Both read the same file.
- **Rootless ports:** rootless Podman can't publish ports below 1024, so keep 8000 and put a proxy in front.
- **Short image names:** the examples use full names (`docker.io/…`), so Podman doesn't ask which registry to pull from.

## Ping without the sysctl

Some platforms don't allow setting `net.ipv4.ping_group_range`. Use `--cap-add NET_RAW` (or `cap_add: [NET_RAW]` in the compose file) instead, or skip ping monitors.

## Hardening

The image runs as an unprivileged user (UID 10001) and needs no write access outside `/tmp`, so you can lock it down further:

```bash
docker run … \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  docker.io/timothestoifl24/statora:latest
```

## Backups

Everything worth keeping is in PostgreSQL:

```bash
docker compose exec -T postgres pg_dump -U statora statora | gzip > statora-$(date +%F).sql.gz
```

Restore into a fresh stack with `gunzip -c backup.sql.gz | docker compose exec -T postgres psql -U statora statora`. Redis needs no backup.

## Updating

See [upgrading](./upgrading) for version pinning, betas and rollbacks. In short:

::: code-group

```bash [Compose]
docker compose pull && docker compose up -d
```

```bash [Without Compose]
docker pull docker.io/timothestoifl24/statora:latest
docker rm -f statora
# run the "docker run" command from step 3 again
```

:::
