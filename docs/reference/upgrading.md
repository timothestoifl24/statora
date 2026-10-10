# Upgrading

Statora applies database migrations automatically when it starts. Upgrading means running a newer image.

::: tip Pin versions in production
Use a release tag such as `0.1.0` rather than `latest`, so upgrades happen when you decide. See [container images](./images).
:::

## Docker Compose

```bash
# .env
STATORA_VERSION=0.2.0
```

```bash
docker compose pull && docker compose up -d
```

## Docker

```bash
docker pull ghcr.io/timothestoifl24/statora:0.2.0
docker rm -f statora   # then start it again with the new tag
```

## Kubernetes

Set `newTag` in `kustomization.yaml` and apply it again. Pods are replaced one at a time, and migrations are serialized with a database lock.

```bash
kubectl apply -k .
kubectl -n statora rollout status deployment/statora
```

## Before you upgrade

1. Read the [changelog](./changelog) for anything marked **breaking**.
2. Take a database backup: `pg_dump -U statora statora > backup.sql`.

## Upgrading PostgreSQL to a new major version

The compose file and the Kubernetes manifests use PostgreSQL 18. PostgreSQL can't open a data directory from an older major version, so moving an existing database from, for example, 17 to 18 means dump and restore:

```bash
docker compose exec -T postgres pg_dump -U statora -Fc statora > statora.dump   # still on the old version
docker compose down
# switch the image to postgres:18-alpine and the volume mount to /var/lib/postgresql,
# using a new volume name so the old data stays untouched until you're done
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U statora -d statora --no-owner < statora.dump
docker compose up -d
```

::: warning The volume path changed in PostgreSQL 18
The official image keeps its data in `/var/lib/postgresql/18/docker` and expects the volume at `/var/lib/postgresql`. With the old mount (`/var/lib/postgresql/data`) the container refuses to start.
:::

## Rolling back

Migrations only move forward automatically. To go back to an older version, restore the backup taken before the upgrade, then start the older image.
