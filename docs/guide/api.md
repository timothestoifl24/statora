# API & automation

Everything in the admin panel is also available over a REST API at `/api/v1`. The OpenAPI 3.1 schema is served at `/api/openapi.json`, with interactive docs at `/api/docs` (Swagger UI) and `/api/redoc`.

## Tokens

Send a token as a bearer header:

```bash
curl -H "Authorization: Bearer st_…" https://status.example.com/api/v1/monitors
```

There are two ways to get a token:

- **In the UI**: *Profile → API tokens*. You choose a name, the scopes and an optional expiry, and the token is shown once.
- **With credentials**: for local and LDAP accounts. SAML and OIDC users create tokens in the UI.

```bash
curl -X POST https://status.example.com/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "ci", "password": "…", "name": "terraform", "scopes": ["read", "write"]}'
```

A `read` token can only call `GET` endpoints. A token can never do more than its user's role allows. Only a hash of each token is stored.

## Conventions

- Every resource has list, get, create, `PATCH` and `DELETE`, plus `PUT` where a full replacement makes sense. `DELETE` is idempotent.
- List endpoints are paginated (`limit`, `offset`) and filterable, for example `?name=` or `?slug=`, which is what Terraform data sources need.
- Errors always look like `{"detail": …, "code": "not_found"}`.
- Operation IDs are stable (`create_monitor`, `get_status_page`, …), so generated clients don't change from release to release.

See the [REST API reference](/reference/api) for the endpoint list.

## Terraform

The API is designed to be wrapped by a Terraform provider: server-assigned IDs, full CRUD, write-only secrets and filterable lists. Until a dedicated provider exists, the generic [`restapi`](https://registry.terraform.io/providers/Mastercard/restapi/latest) provider works:

```hcl
provider "restapi" {
  uri                  = "https://status.example.com/api/v1"
  write_returns_object = true
  headers = { Authorization = "Bearer ${var.statora_token}" }
}

resource "restapi_object" "website" {
  path = "/monitors"
  data = jsonencode({
    name       = "Website"
    type       = "http"
    target     = "https://example.com"
    interval_s = 60
  })
}
```
