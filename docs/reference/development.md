# Development

You need Python 3.13 or newer (3.15 is what the container image uses), [uv](https://docs.astral.sh/uv/), and Docker or Podman for PostgreSQL and Redis. CI tests Python 3.13 to 3.15 against PostgreSQL 18 and Redis 8.8.

::: info SAML support on Python 3.15
`xmlsec`, which SAML uses, doesn't publish packages for Python 3.15 yet, so it's compiled from source. Install its system libraries first, and build `lxml` against the same `libxml2`:

```bash
brew install libxmlsec1 pkg-config                                    # macOS
sudo apt install pkg-config libxml2-dev libxslt1-dev libxmlsec1-dev   # Debian/Ubuntu
uv sync --all-extras --no-binary-package xmlsec --no-binary-package lxml
```

On Python 3.13–3.14, a plain `uv sync --all-extras` is enough.
:::

```bash
git clone https://github.com/timothestoifl24/statora.git && cd statora
docker compose -f docker-compose.dev.yml up -d   # PostgreSQL :5432, Redis :6379
uv sync --all-extras
uv run statora init --seed                       # migrate, create admin, demo data
uv run statora dev                               # http://localhost:8000, auto-reload
```

## Branches

`main` is production and `develop` is the integration branch: pull requests go to `develop`, and `develop` is merged into `main` for a release. The [contributing guidelines](https://github.com/timothestoifl24/statora/blob/develop/CONTRIBUTING.md) describe the flow, and every pull request has to confirm that its author has read and accepts them.

## Tests and linting

```bash
uv run pytest                                    # uses the dev compose services
uv run ruff check src tests && uv run ruff format src tests
```

- **Integration tests** use a separate `statora_test` database and Redis DB 15, and skip themselves when the services aren't reachable.
- **LDAP tests** need the OpenLDAP container: `docker compose -f docker-compose.dev.yml --profile sso up -d openldap`. The same profile starts Keycloak on port 8080 for trying OIDC and SAML by hand.

## Database migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run statora migrate
```

## Documentation site

This site lives in `docs/` and is built with VitePress:

```bash
cd docs && npm ci && npm run docs:dev
```

## Brand assets

Logos and icons are generated from `branding/make_brand.py`, and the generator also refreshes the copies the app serves:

```bash
uv run --no-project --with resvg-py --with pillow --with fonttools --with uharfbuzz python branding/make_brand.py
```
