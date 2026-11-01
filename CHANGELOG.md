# Changelog

All notable changes to Statora are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Statora follows [Semantic Versioning](https://semver.org/).

Changes collect under the upcoming version while it's being developed, and you can try them with the [`beta` image](https://statora.timothestoifl24.dev/reference/images#beta-preview-of-the-next-release). The date is set when the version is released. Each section also appears in the matching [GitHub release](https://github.com/timothestoifl24/statora/releases).

## [1.2.0] - Unreleased

### Added

- **First-run setup:** on a fresh instance the first visit asks you to create the admin account instead of showing the sign-in page. This initial admin can't be deleted, disabled or demoted, and `statora reset-admin` resets its password. On existing instances, the oldest local admin becomes the initial admin. The API's user objects have a new `is_initial_admin` field.
- **Monitor dashboard:** a summary bar shows how many monitors are up and how many need attention. Down and degraded monitors come first, tinted, with how long they've been failing. Search and filter chips (Problems, HTTP, TCP, Ping, DNS, SQL, Groups) survive the auto-refresh, groups expand inline to show their members, and `/` focuses the search, `n` opens a new monitor.
- **Tile view and wallboard:** switch the monitor list to tiles, or open `/admin?kiosk=1` for a full-screen wallboard without the sidebar. Failing monitors get bigger tiles with the last error and buttons to report an incident or pause them.
- **Open incidents badge** in the admin navigation.
- **Theme-aware logo:** `/static/brand/logo-auto.svg` switches its wordmark between navy and white with the status page's light or dark theme, so it stays readable in both. Use it as a status page's logo URL in place of `logo.svg` or `logo-dark.svg`.
- **Hide the local sign-in form:** under Authentication → Local accounts, hide the username and password form so the sign-in page only shows your identity providers. It needs at least one enabled provider, comes back by itself if none is left, and `/login?local=1` still shows it for local admins.
- **Monitor icons and links:** give a monitor an icon (pick one of the bundled Font Awesome icons, including brand logos, or upload or link your own image) and a link to the app behind it. Status pages show the icon and link the component name to the app; the monitor list and tiles show them too. New `icon` and `link_url` fields in the monitor API.
- **Status page favicon:** each status page can have its own browser-tab icon, uploaded or as a URL (`favicon` in the API).
- **Image uploads:** `POST /api/v1/media` stores a PNG, JPEG, WebP, GIF, ICO or SVG image (up to 256 KB) in the database and returns a `media:` reference for `favicon` and `icon`. Uploaded SVGs must not contain scripts and are served sandboxed.

### Changed

- **`statora create-admin` is removed**, and so are `statora init`'s `--admin-username`, `--admin-password` and `--admin-email` options. Create the first admin in the web UI, and use `statora reset-admin` to recover it.
- **Container images move to Docker Hub:** images are now published as `docker.io/timothestoifl24/statora`, with the same tags as before. `ghcr.io/timothestoifl24/statora` gets no new images; update the image name in your `docker-compose.yml`, `docker run` command or Kubernetes manifests.
- **Admin layout:** the navigation moved into a sidebar, with the user menu and theme toggle at its bottom.
- **Status pages in the admin panel:** a new overview shows each page's status, favicon and size. Create a page and edit its settings in a dialog; creating a page takes you straight to its components, which have their own editor.
- **Forms in dialogs:** creating and editing monitors (including clone), incidents, maintenance windows, users and authentication providers opens a dialog over the current page instead of a separate page. Validation errors stay in the dialog, and edit dialogs have their Delete button (and for providers, Test connection) in the footer. A newly created provider reopens right away, so its callback URLs are at hand. Direct links still open the full page.
- **Bigger buttons:** the row menus and other icon buttons in the admin panel are at least 32 px, so they're easier to hit.
- **Public status page:** a calmer status card replaces the coloured banner and says how many components are affected. Active incidents show as a timeline inside it, maintenance as a slim strip, and each component shows its uptime next to its status.
- **Fonts and icons:** the admin panel and status pages use Inter and JetBrains Mono, shipped with Statora (no requests to font CDNs). Icons now come from Font Awesome Free instead of Tabler Icons; login buttons for Google, GitHub, GitLab and Microsoft providers show the provider's logo.
- **Python 3.13 or newer:** Python 3.12 is no longer supported; CI tests Python 3.13 to 3.15.

### Security

- **`statora serve` refuses a placeholder secret key:** it now exits with an error instead of a warning when `STATORA_SECRET_KEY` still has the default or the Kubernetes example value. With a known key, anyone could forge a session cookie. Set a long random value (for example `openssl rand -hex 32`) before upgrading.
- **Uploaded images are rebuilt, never stored as uploaded:** raster images (PNG, JPEG, WebP, GIF, ICO) are decoded and re-encoded as a clean PNG (at most 256 px), which removes anything hidden in the file. SVGs are rebuilt from an allowlist of shapes and attributes, without scripts, style sheets, event handlers, links or embedded content. The file type is detected from its contents, oversized dimensions are refused before decoding, and upload requests over 512 KB are refused before they're read.
- **Stricter URLs:** links must be well-formed http(s) URLs without user names or passwords, and image URLs (favicon, logo, monitor icon) must use https. A status page's logo URL is now validated too, and can also be an upload. Logos saved earlier with an http URL stay in the API but are no longer shown; change them to https.
- **Security headers:** every response sends `X-Content-Type-Options`, `Referrer-Policy` and a strict Content-Security-Policy: scripts only load from Statora itself (no inline scripts, no `eval`). The admin panel and sign-in page can't be shown inside another site's frame; status pages still can. `Strict-Transport-Security` is sent when `STATORA_SECURE_COOKIES` is on.
- **NUL characters** in URLs or request bodies are refused with 400 instead of causing a server error.

## [1.1.1] - 2026-10-25

### Changed

- **`statora create-admin` is removed**, and so are `statora init`'s `--admin-username`, `--admin-password` and `--admin-email` options. Create the first admin in the web UI, and use `statora reset-admin` to recover it.
- **Dependencies:** updated FastAPI to 0.158.1, and pydantic-settings, Markdown and joserfc to their latest patch releases.

## [1.1.0] - 2026-10-24

### Added

- **First-run setup:** on a fresh instance the first visit asks you to create the admin account instead of showing the sign-in page. This initial admin can't be deleted, disabled or demoted, and `statora reset-admin` resets its password. On existing instances, the oldest local admin becomes the initial admin. The API's user objects have a new `is_initial_admin` field.
- **SQL monitors:** run a query against PostgreSQL, MySQL/MariaDB, Microsoft SQL Server or Oracle, and check the first value (equals or contains) or a minimum number of rows. Queries run read-only and are rolled back. The password is stored encrypted and never returned by the API. See [Monitors → SQL](https://statora.timothestoifl24.dev/guide/monitors#sql).
- **Status page editor:** reorder groups and monitors by dragging them by their grip handle, and drag a monitor into another group. The arrow buttons still work from the keyboard.
- **Uptime bars per minute, hour or day:** a new "Uptime bars" setting per status page (`history_resolution` in the API) shows the last 2 hours per minute, the last 5 days per hour, or the last 120 days per day. Daily bars now cover 120 days instead of 90.
- **Monitor list options:** each row has a menu to pause or resume the monitor without leaving the list, clone it into a prefilled new-monitor form, or edit it.

### Changed

- **`statora create-admin` is removed**, and so are `statora init`'s `--admin-username`, `--admin-password` and `--admin-email` options. Create the first admin in the web UI, and use `statora reset-admin` to recover it.
- **Dependencies:** updated FastAPI, Pydantic, pydantic-settings, Markdown and fakeredis to their latest patch and minor releases.

### Fixed

- **Monitor page:** a newly created monitor no longer stays on "pending" until you reload. The monitor's page now refreshes itself: every few seconds until the first check is in, then every 15 seconds like the dashboard.

### Security

- **certifi 2026.10.23:** the bundled CA certificates no longer trust the emSign root CAs, whose intermediate CA keys were compromised ([GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)). This affects HTTPS checks and outgoing connections such as OIDC; the container image picks up the new bundle.

## [1.0.0] - 2026-10-11

First stable release.

### Changed

- **`statora create-admin` is removed**, and so are `statora init`'s `--admin-username`, `--admin-password` and `--admin-email` options. Create the first admin in the web UI, and use `statora reset-admin` to recover it.
- **Releases:** a stable release deletes the betas it supersedes, so the `X.Y.Z-beta.N` images, pre-releases and tags up to that version disappear once `X.Y.Z` is out. Pin a stable tag, or follow `beta`, rather than a specific beta.

### Security

- **Redirects:** sign-in return targets (the login `next` parameter, OIDC and SAML) and admin redirects only accept paths on the same site. Previously a target such as `/\t/evil.example` could send users to another host after signing in.
- **SAML:** when the service-provider metadata can't be generated, the reason is logged instead of returned in the response, so key and certificate details are no longer exposed.

## [0.1.0] - 2026-10-11

First public release.

### Added

- **First-run setup:** on a fresh instance the first visit asks you to create the admin account instead of showing the sign-in page. This initial admin can't be deleted, disabled or demoted, and `statora reset-admin` resets its password. On existing instances, the oldest local admin becomes the initial admin. The API's user objects have a new `is_initial_admin` field.
- **Monitors:** HTTP(S), TCP, ping and DNS checks with retries and latency thresholds.
- **Groups:** stack and redundancy groups, nesting, instant re-evaluation when a member changes, and expandable members on status pages.
- **Status pages:** 90-day uptime bars, incidents, maintenance, light/dark toggle, accent colours and an optional "Powered by" footer.
- **Incidents and maintenance:** Markdown timelines, and internal ITSM ticket and change references.
- **Sign-in:** local accounts, LDAP / Active Directory, OAuth2 / OpenID Connect and SAML 2.0, with just-in-time provisioning and group-to-role mapping.
- **REST API:** OpenAPI 3.1, Swagger UI and scoped API tokens.
- **Platform:** Python 3.15 container image; tested on Python 3.12–3.15, PostgreSQL 18 and Redis 8.8.
- **Deployment:** single container image, Docker Compose and Kubernetes manifests, horizontal scaling with a scheduler leader lock, and serialized migrations.
- **Releases:** stable images (`X.Y.Z`, `X.Y`, `latest`) from `main`, beta images (`X.Y.Z-beta.N`, `beta`) from `develop`, and GitHub releases whose notes come from this changelog.

[1.2.0]: https://github.com/timothestoifl24/statora/releases/tag/v1.2.0
[1.1.1]: https://github.com/timothestoifl24/statora/releases/tag/v1.1.1
[1.1.0]: https://github.com/timothestoifl24/statora/releases/tag/v1.1.0
[1.0.0]: https://github.com/timothestoifl24/statora/releases/tag/v1.0.0
[0.1.0]: https://github.com/timothestoifl24/statora/releases/tag/v0.1.0
