# Initial setup

Statora is running ([Docker / Podman](./docker) or [Kubernetes](./kubernetes)); this page takes you from an empty instance to a first status page.

## What happens on first start

1. The app applies its database migrations. They are serialized, so several replicas can start at once.
2. One replica becomes the scheduler leader and starts checking monitors.
3. The web UI comes up on port `8000`. `GET /healthz` reports whether PostgreSQL and Redis are reachable.

## 1. Create the admin account

Open `http://<host>:8000/admin`. On a fresh instance there is no sign-in yet: the page asks you to create the admin account, then signs you in.

::: warning Do this right away
Whoever opens the page first creates the admin, so do this right after starting Statora, before you expose it to the internet.
:::

This first account is the *initial admin*. It can always sign in with its password, even when single sign-on is broken or local login is turned off, and `statora reset-admin` resets its password if you lose it (see the [FAQ](/faq#how-do-i-reset-a-lost-admin-password)).

## 2. Put it behind HTTPS

Before other people use Statora, terminate TLS in a reverse proxy ([examples](./docker#https-with-a-reverse-proxy)) and set:

```ini
STATORA_BASE_URL=https://status.example.com
STATORA_SECURE_COOKIES=true
```

`STATORA_BASE_URL` is also what OIDC and SAML callback URLs are built from, so set it before you connect an identity provider. All settings are listed under [advanced config](./advanced-config).

## 3. Add monitors

Under **Monitors**, add a check for each thing you want to watch: an HTTP endpoint, a TCP port, a host to ping, a DNS record or a database query. Combine monitors into [groups](/guide/groups) when a service is only healthy if all of its parts are, or when one of several nodes is enough. The [monitors guide](/guide/monitors) explains every option.

::: tip Demo data
`statora seed` (for example `docker compose exec app statora seed`) adds demo monitors, a stack and a redundancy group, and a status page at `/s/demo`. Delete them whenever you like.
:::

## 4. Build a status page

Under **Status pages**, create a page, give it a slug (it's served at `/s/<slug>`) and add component groups with the monitors you want to show, under public names. Each page has its own accent colour, logo and favicon. See [status pages](/guide/status-pages).

## 5. Invite your team

- **Local accounts:** add users under **Users** and give each a role: viewer, editor or admin.
- **Single sign-on:** connect LDAP / Active Directory, OIDC or SAML under **Authentication**, and map groups to roles. See [users & sign-in](/guide/authentication).

## 6. Automate (optional)

Create an API token under *Profile → API tokens* to manage Statora from scripts or CI. The [REST API](./api) page has examples and the full OpenAPI spec.
