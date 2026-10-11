# Contributing to Statora

Thanks for helping. Bug reports, fixes, documentation and ideas are all welcome. This page explains how to get a change merged without surprises.

**Please read these guidelines before you open a pull request.** Every pull request has to confirm that you've read and accept them (see [Accepting these guidelines](#accepting-these-guidelines)). By taking part, you also agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Branches

| Branch | Purpose |
|---|---|
| `main` | **Production.** Every new version merged here becomes a release, published as `X.Y.Z`, `X.Y` and `latest` images. |
| `develop` | **Integration.** Reviewed pull requests are merged here first and published as `X.Y.Z-beta.N` and `beta` images for testing. |
| `feature/…`, `fix/…`, `docs/…` | Your work, branched from `develop`. |
| `hotfix/…` | Urgent production fixes, branched from `main` (maintainers only). |

Open your pull requests against **`develop`**. Pull requests from other branches into `main` are rejected by CI.

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

1. **Fork and branch** from `develop`, for example `fix/ping-timeout` or `feature/smtp-monitor`.
2. **Keep the scope small:** one topic per pull request.
3. **Add or update tests** for any change in behaviour. Tests live in `tests/`. Integration tests use the dev PostgreSQL and Redis; LDAP tests need `docker compose -f docker-compose.dev.yml --profile sso up -d openldap`.
4. **Update the docs** in `docs/` when something users see changes, and add an entry to [`CHANGELOG.md`](CHANGELOG.md) (see [Changelog](#changelog)).
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

## Changelog

[`CHANGELOG.md`](CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add your entry under the upcoming version at the top (`## [X.Y.Z] - Unreleased`), in the group that fits:

- **Added:** new features
- **Changed:** changes to existing behaviour
- **Deprecated:** features that will be removed
- **Removed:** features that were removed
- **Fixed:** bug fixes
- **Security:** vulnerability fixes

Write for people who run Statora: what changed for them, not how the code changed. Mark changes that need action when upgrading with **Breaking:**. The section is copied into the GitHub release for every beta and for the final release, and the website shows the same file.

## Accepting these guidelines

The pull request template ends with this checkbox:

> - [x] I have read and accept the contributing guidelines, including that my contribution is licensed under the MIT License.

Tick it when you open the pull request. The **Guidelines accepted** check stays red, and the pull request can't be merged, until it is; editing the description re-runs the check.

By ticking it, you confirm that:

1. you have read these guidelines and the [Code of Conduct](CODE_OF_CONDUCT.md), and will follow them;
2. your contribution is your own work, or you have the right to submit it, and any third-party code in it is identified together with its license;
3. your contribution is licensed under the project's [MIT License](LICENSE), the same license everyone else receives Statora under. You keep the copyright in your work.

## Review

- A maintainer will review your pull request. Expect questions and suggestions; they're part of getting good code in, not a judgement of you.
- CI must be green: lint, tests, the guidelines check, and the container image and docs builds when they're affected.
- Pull requests into `develop` are usually squash-merged, so feel free to push fix-up commits while the review is going on.

## Releases (maintainers)

Releases are automated; the version in `pyproject.toml` decides everything. On `develop` it always holds the **next** version to be released.

| Event | Result |
|---|---|
| Merge into `develop` | Beta images `X.Y.Z-beta.N` and `beta`, and a GitHub pre-release `vX.Y.Z-beta.N` |
| Merge into `main` with a new version | Images `X.Y.Z`, `X.Y` and `latest`, and the GitHub release `vX.Y.Z` |
| Merge into `main` with an already released version | Nothing is published |

To release:

1. On `develop`, change the heading of the upcoming version in `CHANGELOG.md` from `- Unreleased` to today's date, for example `## [0.2.0] - 2026-11-03`. CI refuses to release from `main` without a dated, non-empty section.
2. Open a pull request from `develop` to `main`, and merge it with a **merge commit** (not squash), so both branches share their history. CI creates the tag, the images and the release; there's nothing to tag by hand.
3. Straight afterwards, on `develop`, bump `project.version` in `pyproject.toml` to the next version (for example `0.3.0`) and add a new `## [0.3.0] - Unreleased` section at the top of `CHANGELOG.md`. Until you do, the beta builds on `develop` fail with a reminder.

Hotfixes branch from `main` as `hotfix/…`, bump the patch version (for example `0.2.1`), go into `main` through a pull request, and are then merged back into `develop`.

## Reporting bugs and requesting features

Use the [issue forms](https://github.com/timothestoifl24/statora/issues/new/choose). For bugs, the Statora version, how you run it (Docker, Compose, Kubernetes) and the steps to reproduce make the difference between a quick fix and a long back-and-forth.
