# Releasing Statora

Notes for the maintainer. Contributors don't need to do any of this: their pull requests go to `develop` and are labelled from the pull request checklist.

Releases are automated; the version in `pyproject.toml` decides everything. On `develop` it always holds the **next** version to be released.

| Event | Result |
|---|---|
| Push to a pull request into `develop` | Image `develop-pr-N`, replacing the previous one, and a comment on the pull request how to pull it (not for pull requests from forks or Dependabot) |
| Pull request into `develop` merged or closed | Image `develop-pr-N` is deleted |
| Merge into `develop` | Beta images `X.Y.Z-beta.N` and `beta`, and a GitHub pre-release `vX.Y.Z-beta.N` |
| Merge into `main` with a new version | Images `X.Y.Z`, `X.Y` and `latest`, and the GitHub release `vX.Y.Z` |
| Merge into `main` with an already released version | Nothing is published |

To release:

1. On `develop`, change the heading of the upcoming version in `CHANGELOG.md` from `- Unreleased` to today's date, for example `## [0.2.0] - 2026-11-03`. CI refuses to release from `main` without a dated, non-empty section.
2. Open a pull request from `develop` to `main` (it doesn't need the pull request template; replace it with a short description), and merge it with a **merge commit** (not squash), so both branches share their history. CI creates the tag, the images and the release; there's nothing to tag by hand.
3. Straight afterwards, on `develop`, bump `project.version` in `pyproject.toml` to the next version (for example `0.3.0`) and add a new `## [0.3.0] - Unreleased` section at the top of `CHANGELOG.md`. Until you do, the beta builds on `develop` fail with a reminder.

Hotfixes branch from `main` as `hotfix/…`, bump the patch version (for example `0.2.1`), go into `main` through a pull request (no template needed), and are then merged back into `develop`.

Deleting images (betas after a release, pull request images after merge or close) needs the repository to have the **Admin** role on the `statora` package: package settings → Manage Actions access.

## Changelog

[`CHANGELOG.md`](CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries for the upcoming version go under `## [X.Y.Z] - Unreleased`, grouped as **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed** and **Security**, and written for people who run Statora. Mark changes that need action when upgrading with **Breaking:**.

- **Release notes:** the section for a version is copied into its GitHub release, and into every beta of it. GitHub's list of merged pull requests follows, grouped by their labels (see `.github/release.yml`), which helps when writing the entries.
- **Where it's shown:** the website shows the same file at https://statora.stoifl.app/reference/changelog.
