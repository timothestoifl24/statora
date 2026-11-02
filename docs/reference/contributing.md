---
title: Contributing
description: Development setup, running the tests, and the conventions this codebase keeps.
---

# Contributing

Bug reports, small fixes and larger changes are all welcome. For anything larger than a small fix, such as a new feature, a new monitor type or a change to the API or database schema, opening an [issue](https://github.com/timothestoifl24/statora/issues) first to agree on the approach will save you a rewrite.

::: danger Found a security issue?
Do not open a public issue. See the [security policy](./security) for how to report it privately.
:::

## Development setup

You need Python 3.13 or newer, [uv](https://docs.astral.sh/uv/), and Docker or Podman for PostgreSQL and Redis. CI tests Python 3.13 to 3.15 against PostgreSQL 18 and Redis 8.8, on Linux.

::: tip Windows
Use [WSL 2](https://learn.microsoft.com/windows/wsl/install) with Ubuntu and follow the **Debian / Ubuntu** tabs. Statora is built and tested on Linux only; Docker Desktop or Podman Desktop provide the containers inside WSL.
:::

### 1. Install uv

::: code-group

```bash [macOS]
brew install uv
```

```bash [Linux / WSL]
curl -LsSf https://astral.sh/uv/install.sh | sh
```

:::

### 2. Get the code and start PostgreSQL and Redis

```bash
git clone https://github.com/timothestoifl24/statora.git && cd statora
docker compose -f docker-compose.dev.yml up -d   # PostgreSQL :5432, Redis :6379
```

With Podman, use `podman compose` instead of `docker compose`, here and below.

### 3. Install the dependencies

On Python 3.13 and 3.14, this is all:

```bash
uv sync --all-extras
```

On Python 3.15, `xmlsec` (used for SAML) has no prebuilt packages yet, so it's compiled from source. Install a compiler and its system libraries first, then build `lxml` against the same `libxml2`:

::: code-group

```bash [macOS]
xcode-select --install   # compiler, if you don't have it yet
brew install libxmlsec1 pkg-config
uv sync --all-extras --no-binary-package xmlsec --no-binary-package lxml
```

```bash [Debian / Ubuntu]
sudo apt install build-essential pkg-config libxml2-dev libxslt1-dev libxmlsec1-dev libxmlsec1-openssl
uv sync --all-extras --no-binary-package xmlsec --no-binary-package lxml
```

```bash [Fedora / RHEL]
sudo dnf install gcc pkgconf-pkg-config libxml2-devel libxslt-devel xmlsec1-devel xmlsec1-openssl-devel
uv sync --all-extras --no-binary-package xmlsec --no-binary-package lxml
```

:::

### 4. Run it

```bash
uv run statora init --seed   # migrate, add demo data
uv run statora dev           # http://localhost:8000, auto-reload
```

- **Admin panel:** <http://localhost:8000/admin>. The first visit asks you to create the admin account.
- **Demo status page:** <http://localhost:8000/s/demo>, also served at `/`.
- **API docs:** <http://localhost:8000/api/docs>.

`init --seed` creates six demo monitors, including one that is broken on purpose and goes down after its retries, and a demo page with a resolved incident and an upcoming maintenance window.

## Running the tests

```bash
uv run pytest
uv run ruff check src tests && uv run ruff format src tests
```

- **Unit tests** need no services.
- **Integration tests** use the dev compose services, with a separate `statora_test` database and Redis DB 15, and skip themselves when the services aren't reachable.
- **LDAP tests** need the OpenLDAP container: `docker compose -f docker-compose.dev.yml --profile sso up -d openldap`. The same profile starts Keycloak on port 8080 for trying OIDC and SAML by hand.

To point the tests at other services:

::: code-group

```bash [macOS / Linux]
STATORA_TEST_DATABASE_URL=postgresql+asyncpg://statora:statora@db.example:5432/statora_test \
STATORA_TEST_REDIS_URL=redis://db.example:6379/15 \
uv run pytest
```

```powershell [Windows (PowerShell)]
$env:STATORA_TEST_DATABASE_URL = "postgresql+asyncpg://statora:statora@db.example:5432/statora_test"
$env:STATORA_TEST_REDIS_URL = "redis://db.example:6379/15"
uv run pytest
```

:::

::: warning Point it at a scratch database, never a real one
The suite migrates that database and empties every table before each test.
:::

CI runs lint and the tests on Python 3.13 to 3.15 for every pull request.

If you change the container image, build it and check that it starts before opening a pull request:

```bash
docker build -t statora .
docker run --rm statora --help   # the entrypoint is the statora command
```

## Database migrations

Create a migration after changing the models, and check what it generated:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run statora migrate
```

Never edit a migration that has been released.

## Code style

Ruff enforces formatting and lint rules (line length 110). Beyond that, the existing code is the style guide. A few conventions worth keeping:

- **Comment the *why*, not the *what*.** A comment earns its place by explaining something that isn't obvious from reading the code: a workaround, an ordering requirement, a security property that would silently break if changed.
- **Clear names over comments,** and no abstraction ahead of a second use case.
- **Keep the REST API stable.** Existing paths, fields and operation IDs stay as they are, since scripts and API clients depend on them. Additive changes are fine; breaking ones need discussion first.
- **No build step for the front end.** Plain Jinja2, HTMX and small vanilla JavaScript. New static assets go through `asset()`, so browsers pick up changes.
- **No inline scripts and no CDN.** The Content-Security-Policy forbids inline scripts (a test checks every template), and every asset is vendored, so Statora works on an isolated network.

## Commit messages

A short summary in the imperative mood (`Add DNS-over-HTTPS monitor`, not `fixed stuff`), with a body explaining *why* when it isn't obvious.

Don't edit `CHANGELOG.md`: the maintainer writes it when releasing, from the pull request titles and descriptions.

## Before opening a pull request

- [ ] `uv run pytest` passes, and `uv run ruff check src tests` and `uv run ruff format --check src tests` are clean.
- [ ] New behaviour has a test. A bug fix has a test that **fails without the fix**.
- [ ] Database changes come with a new Alembic migration.
- [ ] These docs are updated if you changed a setting, an endpoint or anything users see.
- [ ] No secrets, `.env` or local database files are staged.

## Describing your pull request

Pull requests go to `develop`. The **title** says what changed, written for someone running Statora (`Fix ping monitors timing out on IPv6`, not `Update ping.py`). The **description** says what users will notice and why the change is needed.

The pull request template also asks two short questions; tick every box that applies:

- **Type of change** (at least one): bug fix, new feature, breaking change, documentation, refactoring, API changes, performance, tests.
- **AI usage:** whether AI was used to write or to review the change. Leave both empty if it wasn't. Using AI is fine; reviews just take it into account.

The pull request is **labelled automatically** from these boxes (`bug`, `enhancement`, `breaking-change`, …, `ai-written`, `ai-reviewed`), and the labels follow when you change the boxes later. They sort the change into the right section of the release notes, so pick **Breaking change** for anything that needs action when upgrading.

Other labels are added for you: `area: …` and `chore` from the files you change, `security` from a `security/…` branch or a title that mentions security or a CVE, and `hotfix` / `release` from the branch.

## Trying your pull request's image

Every pull request into `develop` from a branch of this repository gets its own container image, `docker.io/timothestoifl24/statora:develop-pr-N` (N is the pull request number). A comment on the pull request shows how to pull it. Each push rebuilds it and replaces the previous one, and the image is deleted when the pull request is merged or closed. Pull requests from forks are built and tested, but get no published image.

A pull request that only changes documentation (files under `docs/` and Markdown files at the top level) skips lint, the tests and the image build, and gets no image; the docs check builds the site instead. Pull requests into `main` and pushes to `main` always run everything.

## Accepting these guidelines

The pull request template ends with this checkbox:

> - [x] I have read and accept the contributing guidelines, including that my contribution is licensed under the MIT License.

Tick it when you open the pull request, together with at least one **Type of change**. The **Guidelines accepted** check stays red, and the pull request can't be merged, until both are done; editing the description re-runs the check.

By ticking it, you confirm that:

1. you have read the [contributing guidelines](https://github.com/timothestoifl24/statora/blob/develop/CONTRIBUTING.md) and the [Code of Conduct](https://github.com/timothestoifl24/statora/blob/develop/CODE_OF_CONDUCT.md), and will follow them;
2. your contribution is your own work, or you have the right to submit it, and any third-party code in it is identified together with its license;
3. your contribution is licensed under the project's [MIT License](https://github.com/timothestoifl24/statora/blob/develop/LICENSE), the same license everyone else receives Statora under. You keep the copyright in your work.

## Working on the documentation site

This site is built with [VitePress](https://vitepress.dev/) from `docs/`. It's the only part of the repository that needs Node.

```bash
cd docs
npm ci
npm run docs:dev        # http://localhost:5173, hot reload
npm run docs:build      # writes docs/.vitepress/dist
```

No Node installed? Run it in a container, from the repository root:

::: code-group

```bash [macOS / Linux]
docker run --rm -it -v "$PWD:/repo" -w /repo/docs -p 5173:5173 docker.io/library/node:22-alpine \
  sh -c "apk add --no-cache git && git config --global --add safe.directory /repo && npm ci && npm run docs:dev -- --host 0.0.0.0"
```

```powershell [Windows (PowerShell)]
docker run --rm -it -v "${PWD}:/repo" -w /repo/docs -p 5173:5173 docker.io/library/node:22-alpine `
  sh -c "apk add --no-cache git && git config --global --add safe.directory /repo && npm ci && npm run docs:dev -- --host 0.0.0.0"
```

:::

::: tip Why the whole repository, and git
The Changelog and Security policy pages include `CHANGELOG.md` and `SECURITY.md` from the repository root, so the build needs more than `docs/`. And `lastUpdated` reads each page's commit date, so it needs `git` too; without it the build fails with `spawn git ENOENT`.
:::

::: warning The container installs Linux packages into docs/node_modules
Delete `docs/node_modules` before going back to `npm` on macOS or Windows.
:::

The REST API page offers the OpenAPI spec, which the Pages workflow writes for each branch. To have it locally too:

```bash
uv run python scripts/export_openapi.py docs/public/openapi.json
```

A dead internal link fails the build. CI builds the site for every pull request that touches it.

## Brand assets

Logos and icons are generated by `branding/make_brand.py`, which also refreshes the copies the app serves:

```bash
uv run --no-project --with resvg-py --with pillow --with fonttools --with uharfbuzz python branding/make_brand.py
```

## Releasing (maintainers)

Releases from `develop` to `main` are done by the maintainer and are mostly automated; see [RELEASING.md](https://github.com/timothestoifl24/statora/blob/develop/RELEASING.md) for how.
