# Docker

Run the three containers yourself, for example when you manage containers with your own tooling or already run PostgreSQL. For most single-host installs, [Docker Compose](./docker-compose) is less typing.

## 1. Network and secrets

```bash
docker network create statora

export POSTGRES_PASSWORD=$(openssl rand -hex 16)
export STATORA_SECRET_KEY=$(openssl rand -hex 32)
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"   # store both somewhere safe
echo "STATORA_SECRET_KEY=$STATORA_SECRET_KEY"
```

## 2. PostgreSQL and Redis

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

## 3. Statora

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

## 4. First admin

```bash
docker exec -it statora statora create-admin
```

Then open <http://localhost:8000/admin>.

## Hardening

The image runs as an unprivileged user (UID 10001) and needs no write access outside `/tmp`, so you can lock it down further:

```bash
docker run … \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  docker.io/timothestoifl24/statora:latest
```

## Ping without the sysctl

Some platforms don't allow setting `net.ipv4.ping_group_range`. Use `--cap-add NET_RAW` instead, or skip ping monitors.

## Updating

```bash
docker pull docker.io/timothestoifl24/statora:latest
docker rm -f statora
# run the "docker run" command from step 3 again
```

Migrations run automatically. See [upgrading](/reference/upgrading) for version pinning and rollbacks.
