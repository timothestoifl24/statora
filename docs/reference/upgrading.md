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

## Rolling back

Migrations only move forward automatically. To go back to an older version, restore the backup taken before the upgrade, then start the older image.
