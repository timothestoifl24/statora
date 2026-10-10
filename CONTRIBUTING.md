# Contributing to Statora

Thanks for helping. Bug reports, fixes, documentation and ideas are all welcome. This page explains how to get a change merged without surprises.

By taking part, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- **Found a security problem?** Don't open an issue. Report it privately as described in [SECURITY.md](SECURITY.md).
- **Small fixes**, such as typos, obvious bugs and documentation, can go straight to a pull request.
- **Anything bigger**, such as a new feature, a new monitor type or a change to the API or database schema: please open an issue or a discussion first, so we can agree on the approach before you spend time on it.
- Search the existing [issues](https://github.com/timothestoifl24/statora/issues) first; someone may already be on it.

## Development setup

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and Docker or Podman.

```bash
git clone https://github.com/timothestoifl24/statora.git && cd statora
docker compose -f docker-compose.dev.yml up -d   # PostgreSQL 18, Redis 8.8
uv sync --all-extras
uv run statora init --seed
uv run statora dev                               # http://localhost:8000
```

On Python 3.15, SAML's `xmlsec` is compiled from source and needs system libraries. The [development guide](https://statora.stoifl.app/reference/development) has the details, and also covers the docs site and the brand assets.

## Making a change

1. **Fork and branch** from `main`, for example `fix/ping-timeout` or `feature/smtp-monitor`.
2. **Keep the scope small:** one topic per pull request.
3. **Add or update tests** for any change in behaviour. Tests live in `tests/`. Integration tests use the dev PostgreSQL and Redis; LDAP tests need `docker compose -f docker-compose.dev.yml --profile sso up -d openldap`.
4. **Update the docs** in `docs/` when something users see changes, and add a line to `docs/reference/changelog.md`.
5. **Run the checks:**

   ```bash
   uv run ruff check src tests
   uv run ruff format src tests
   uv run pytest
   ```

   CI runs the same checks on Python 3.12 to 3.15, against PostgreSQL 18 and Redis 8.8.

## Conventions

- **Code:** match the style of the surrounding code; Ruff enforces formatting and lint rules. Prefer clear names over comments, and comment the *why*, not the *what*.
- **Database changes:** create a migration with `uv run alembic revision --autogenerate -m "describe the change"` and check what it generated. Never edit a migration that has been released.
- **REST API:** keep existing paths, fields and operation IDs stable; automation and the Terraform workflow depend on them. Additive changes are fine; breaking ones need discussion first.
- **Templates and front end:** no build step; plain Jinja2, HTMX and small vanilla JavaScript. New static assets go through `asset()` so browsers pick up changes.
- **Commit messages:** a short summary in the imperative mood ("Add DNS-over-HTTPS monitor"), with a body explaining *why* when it isn't obvious.

## Contributor License Agreement

Before your first pull request can be merged, you need to accept the [Contributor License Agreement](CLA.md). A bot will comment on your pull request; reply with the sentence it asks for. You only do this once.

The CLA lets the project offer Statora under other terms in the future, alongside the MIT License. You keep the copyright in your work.

## Review

- A maintainer will review your pull request. Expect questions and suggestions; they're part of getting good code in, not a judgement of you.
- CI must be green: lint, tests, and the container image and docs builds when they're affected.
- Pull requests are usually squash-merged, so feel free to push fix-up commits while the review is going on.

## Reporting bugs and requesting features

Use the [issue forms](https://github.com/timothestoifl24/statora/issues/new/choose). For bugs, the Statora version, how you run it (Docker, Compose, Kubernetes) and the steps to reproduce make the difference between a quick fix and a long back-and-forth.
