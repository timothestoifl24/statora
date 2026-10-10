# Kubernetes

The repository ships [Kustomize manifests](https://github.com/timothestoifl24/statora/tree/main/deploy/kubernetes) for Statora with PostgreSQL and Redis. Everything runs in the `statora` namespace under the **restricted** Pod Security Standard: non-root, read-only root filesystem, no Linux capabilities.

## What gets deployed

| Resource | Purpose |
|---|---|
| `Deployment/statora` (2 replicas) | Web UI, API and checker. Replicas share the work through a Redis leader lock. |
| `StatefulSet/postgres` + 10 Gi PVC | The database. |
| `Deployment/redis` | Caches and coordination, without persistence. |
| `Service` ×3, `Ingress` | Internal services and the public entry point. |
| `Secret/statora-secrets`, `ConfigMap/statora-config` | Generated from `secrets.env` and `config.env`. |

## 1. Get the manifests

```bash
git clone --depth 1 https://github.com/timothestoifl24/statora.git
cd statora/deploy/kubernetes
cp secrets.env.example secrets.env
cp config.env.example config.env
```

## 2. Configure

`secrets.env` (git-ignored, never commit it):

```ini
STATORA_SECRET_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=<openssl rand -hex 16>
STATORA_DATABASE_URL=postgresql+asyncpg://statora:<same password>@postgres:5432/statora
```

`config.env`:

```ini
STATORA_BASE_URL=https://status.example.com
STATORA_REDIS_URL=redis://redis:6379/0
STATORA_SECURE_COOKIES=true
```

Then edit `ingress.yaml`: set your host, and uncomment `ingressClassName` and the cert-manager annotation if you use them.

## 3. Deploy

```bash
kubectl apply -k .
kubectl -n statora rollout status deployment/statora
kubectl -n statora exec -it deploy/statora -- statora create-admin
```

## Pinning a version

`kustomization.yaml` pins the image tag:

```yaml
images:
  - name: ghcr.io/timothestoifl24/statora
    newTag: "0.1.0"
```

Change `newTag` and run `kubectl apply -k .` again to upgrade. Pods roll one by one, and migrations are serialized with a database lock, so it doesn't matter which pod starts first.

## Using an overlay

Rather than editing the files in place, keep your settings in an overlay:

```yaml
# my-statora/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - https://github.com/timothestoifl24/statora//deploy/kubernetes?ref=v0.1.0
secretGenerator:
  - name: statora-secrets
    behavior: replace
    envs: [secrets.env]
configMapGenerator:
  - name: statora-config
    behavior: replace
    envs: [config.env]
patches:
  - target: { kind: Ingress, name: statora }
    patch: |-
      - op: replace
        path: /spec/rules/0/host
        value: status.example.com
      - op: replace
        path: /spec/tls/0/hosts/0
        value: status.example.com
```

## Using a managed database

To use a managed PostgreSQL service (RDS, Cloud SQL, Azure Database, or an operator such as CloudNativePG):

1. Remove `postgres.yaml` from `resources:` in `kustomization.yaml`.
2. Point `STATORA_DATABASE_URL` at the managed instance.

The same applies to Redis: any Redis 6+ works.

## Probes and ping

- **Readiness** uses `/healthz`, which also reports database and Redis problems, so traffic stops going to a pod that can't serve.
- **Liveness** only checks that the port is open, so a database outage doesn't trigger pointless restarts.
- **Ping monitors** need the sysctl `net.ipv4.ping_group_range`. It's on the Kubernetes "safe" list, so it's allowed by default and set in the pod spec.

## Network policies

If your cluster enforces NetworkPolicies, Statora needs:
- egress to PostgreSQL (5432), Redis (6379) and DNS;
- egress to everything you monitor;
- ingress from your Ingress controller on port 8000.
