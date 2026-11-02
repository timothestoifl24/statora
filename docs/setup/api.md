# REST API

Base path: `/api/v1`. Authentication: `Authorization: Bearer st_…` (see [API & automation](/guide/api) for tokens and conventions).

## OpenAPI spec

The OpenAPI 3.1 spec of this version is published with these docs. Import it into [Bruno](https://www.usebruno.com) with one click, or download it for Postman, Insomnia or a client generator:

<ApiSpec />

The spec lists `http://localhost:8000` as its server: after importing, point the base URL at your instance and set your API token as the bearer token. Your instance also serves its own spec at `/api/openapi.json`, with Swagger UI at `/api/docs` and ReDoc at `/api/redoc`.

## Endpoints

| Area | Endpoints |
|---|---|
| **Auth** | `POST /auth/token` — token from username + password |
| **Me** | `GET /me` · `GET/POST /tokens` · `DELETE /tokens/{id}` |
| **Monitors** | `GET/POST /monitors` · `GET/PATCH/PUT/DELETE /monitors/{id}` · `GET /monitors/{id}/heartbeats` · `GET /monitors/{id}/uptime` |
| **Status pages** | `GET/POST /status-pages` · `GET/PATCH/PUT/DELETE /status-pages/{id}` |
| **Incidents** | `GET/POST /incidents` · `GET/PATCH/DELETE /incidents/{id}` · `POST /incidents/{id}/updates` |
| **Maintenance** | `GET/POST /maintenances` · `GET/PATCH/PUT/DELETE /maintenances/{id}` |
| **Users** (admin) | `GET/POST /users` · `GET/PATCH/DELETE /users/{id}` |
| **Auth providers** (admin) | `GET/POST /auth-providers` · `GET/PATCH/DELETE /auth-providers/{id}` · `POST /auth-providers/{id}/test` |
| **Public** (no auth) | `GET /public/pages/{slug}/summary` |

## Examples

Create an HTTP monitor:

```bash
curl -X POST "$STATORA/api/v1/monitors" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "name": "Website", "type": "http", "target": "https://example.com",
  "interval_s": 60, "retries": 1,
  "config": {"expected_status": ["200-299"], "keyword": "Welcome", "degraded_threshold_ms": 1500}
}'
```

Open an incident and post an update:

```bash
curl -X POST "$STATORA/api/v1/incidents" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "page_id": 1, "title": "Elevated error rates", "impact": "major",
  "message": "We are investigating.", "monitor_ids": [2], "ticket_number": "INC0012345"
}'

curl -X POST "$STATORA/api/v1/incidents/1/updates" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status": "resolved", "body": "A faulty deployment was rolled back."}'
```

## Errors

| Code | `code` | When |
|---|---|---|
| 401 | `unauthenticated`, `invalid_token`, `invalid_credentials` | Missing, invalid, expired or revoked token; wrong password. |
| 403 | `insufficient_scope`, `forbidden` | Read-only token used for a write, or the role doesn't allow it. |
| 404 | `not_found` | |
| 409 | `conflict` | Duplicate username or provider name. |
| 422 | `validation_error`, `invalid_reference` | Invalid input, unknown IDs, group loops. |
| 429 | `rate_limited` | Too many login attempts. |
