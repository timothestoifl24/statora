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

Maintainers put the Jira issue key after the prefix, such as `feature/APP-42-smtp-monitor`, so the work shows up in Jira. You don't need one; a plain `feature/smtp-monitor` is fine.

## Before you start

- **Found a security problem?** Don't open an issue. Report it privately as described in [SECURITY.md](SECURITY.md).
- **Small fixes**, such as typos, obvious bugs and documentation, can go straight to a pull request.
- **Anything bigger**, such as a new feature, a new monitor type or a change to the API or database schema: please open an issue or a discussion first, so we can agree on the approach before you spend time on it.
- Search the existing [issues](https://github.com/timothestoifl24/statora/issues) first; someone may already be on it.

## Development setup

You need Python 3.13 or newer, [uv](https://docs.astral.sh/uv/), and Docker or Podman.

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
4. **Update the docs** in `docs/` when something users see changes.
5. **Run the checks:**

   ```bash
   uv run ruff check src tests
   uv run ruff format src tests
   uv run pytest
   ```

   CI runs the same checks on Python 3.13 to 3.15, against PostgreSQL 18 and Redis 8.8.

## Conventions

- **Code:** match the style of the surrounding code; Ruff enforces formatting and lint rules. Prefer clear names over comments, and comment the *why*, not the *what*.
- **Database changes:** create a migration with `uv run alembic revision --autogenerate -m "describe the change"` and check what it generated. Never edit a migration that has been released.
- **REST API:** keep existing paths, fields and operation IDs stable; automation and the Terraform workflow depend on them. Additive changes are fine; breaking ones need discussion first.
- **Templates and front end:** no build step; plain Jinja2, HTMX and small vanilla JavaScript. New static assets go through `asset()` so browsers pick up changes.
- **Commit messages:** a short summary in the imperative mood ("Add DNS-over-HTTPS monitor"), with a body explaining *why* when it isn't obvious.

## Describing your pull request

The pull request template is for pull requests into `develop`. It asks two short questions. Tick every box that applies:

- **Type of change** (at least one): bug fix, new feature, breaking change, documentation, refactoring, API changes, performance, tests.
- **AI usage:** whether AI was used to write or to review the change. Leave both empty if it wasn't. Using AI is fine; we just want to know, so reviews can take it into account.

The pull request is **labelled automatically** from these boxes (`bug`, `enhancement`, `breaking-change`, …, `ai-written`, `ai-reviewed`), and the labels follow when you change the boxes later. The labels sort your change into the right section of the release notes, so please pick carefully, especially **Breaking change** for anything that needs action when upgrading. You don't need to edit the changelog; the maintainer writes it when releasing.

Other labels are added for you, so you don't need to set any: `area: …` and `chore` from the files you change, `security` from a `security/…` branch or a title that mentions security or a CVE, and `hotfix` / `release` from the branch.

## Trying your pull request's image

Every pull request into `develop` from a branch of this repository gets its own container image, `docker.io/timothestoifl24/statora:develop-pr-N` (N is the pull request number). A comment on the pull request shows how to pull it. Each push rebuilds the image and replaces the previous one, and the image is deleted when the pull request is merged or closed. Pull requests from forks are built and tested, but don't get a published image.

## Accepting these guidelines

The pull request template ends with this checkbox:

> - [x] I have read and accept the contributing guidelines, including that my contribution is licensed under the MIT License.

Tick it when you open the pull request, together with at least one **Type of change**. The **Guidelines accepted** check stays red, and the pull request can't be merged, until both are done; editing the description re-runs the check.

By ticking it, you confirm that:

1. you have read these guidelines and the [Code of Conduct](CODE_OF_CONDUCT.md), and will follow them;
2. your contribution is your own work, or you have the right to submit it, and any third-party code in it is identified together with its license;
3. your contribution is licensed under the project's [MIT License](LICENSE), the same license everyone else receives Statora under. You keep the copyright in your work.

## Review

- A maintainer will review your pull request. Expect questions and suggestions; they're part of getting good code in, not a judgement of you.
- CI must be green: lint, tests, the guidelines check, and the container image and docs builds when they're affected.
- Releases from `develop` to `main` are done by the maintainer; see [RELEASING.md](RELEASING.md) if you're curious how.
- Pull requests into `develop` are usually squash-merged, so feel free to push fix-up commits while the review is going on.

## Reporting bugs and requesting features

Use the [issue forms](https://github.com/timothestoifl24/statora/issues/new/choose). For bugs, the Statora version, how you run it (Docker, Compose, Kubernetes) and the steps to reproduce make the difference between a quick fix and a long back-and-forth.
