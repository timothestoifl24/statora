---
layout: home
title: Self-hosted uptime monitoring and status pages

hero:
  name: Statora
  text: Know it's up. Tell everyone when it isn't.
  tagline: Uptime checks, public status pages, incidents and maintenance in one self-hosted container, with LDAP, OIDC and SAML sign-in and an API you can drive from Terraform.
  image:
    src: /brand/icon.svg
    alt: Statora
  actions:
    - theme: brand
      text: Set it up
      link: /setup/
    - theme: alt
      text: Read the guide
      link: /guide/
    - theme: alt
      text: See it
      link: /screenshots

features:
  - icon: 🩺
    title: HTTP, TCP, ping and DNS
    details: Status codes, keywords, headers and TLS for HTTP; open ports; ICMP without root; any DNS record with an expected value. Retries and a latency threshold for "degraded" on every check.
  - icon: 🧩
    title: Stacks and redundancy groups
    details: A stack is only up when every part is. A redundancy group stays up while enough nodes are, and says "degraded" when one drops out. Groups nest, and react the moment a member changes.
  - icon: 📣
    title: Status pages people trust
    details: As many public pages as you need, with 90-day uptime bars, expandable components, a light/dark switch and your own accent colour. Server-rendered, fast, and working without JavaScript.
  - icon: 🛠️
    title: Incidents and maintenance
    details: Incident timelines written in Markdown, scheduled maintenance that never counts as downtime, and internal ticket or change numbers from your ITSM tool right next to them.
  - icon: 🔐
    title: Sign in the way you already do
    details: Local accounts, LDAP / Active Directory, OpenID Connect (Keycloak, Entra ID, Google, Authentik…) and SAML 2.0, with users created on first login and groups mapped to roles.
  - icon: 🤖
    title: An API made for automation
    details: OpenAPI 3.1 with Swagger UI, stable operation IDs and scoped API tokens. Every resource can be listed, created, updated and deleted, which is what a Terraform provider needs.
  - icon: 📦
    title: One container, your database
    details: The app ships as a single image; PostgreSQL and Redis run beside it. Runs as non-root on a read-only filesystem, with migrations that apply themselves on start-up.
  - icon: ⚖️
    title: Scales sideways
    details: Run as many replicas as you like. They all serve the UI and API, and a Redis leader lock makes sure exactly one of them runs the checks.
  - icon: 🎛️
    title: An admin panel you'll actually like
    details: Built on Tabler, with live dashboards, latency charts, a drag-free page builder, a two-column member picker and dark mode.
---

<div class="home-section">

## See it before you install it

<div class="home-preview">
  <figure class="shot">
    <img src="/screenshots/status-page-light.webp" alt="Public status page with an active incident, maintenance notice and uptime bars" loading="lazy">
    <figcaption>The public status page: overall state, incidents, maintenance and 90 days of history.</figcaption>
  </figure>
  <figure class="shot">
    <img src="/screenshots/dashboard.webp" alt="Admin dashboard listing monitors with their recent checks, uptime and latency" loading="lazy">
    <figcaption>The admin dashboard refreshes itself, so it can stay open on a wall screen.</figcaption>
  </figure>
</div>

[More screenshots →](/screenshots)

## Try it in two minutes

You need Docker (or Podman) with the Compose plugin.

```bash
curl -fsSLO https://raw.githubusercontent.com/timothestoifl24/statora/main/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/timothestoifl24/statora/main/.env.example -o .env

# Set a secret key and a database password
sed -i.bak "s/^STATORA_SECRET_KEY=.*/STATORA_SECRET_KEY=$(openssl rand -hex 32)/; s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" .env

docker compose up -d
docker compose exec app statora create-admin
```

Open <http://localhost:8000/admin>, sign in, and add your first monitor. Want something to look at straight away? `docker compose exec app statora seed` creates demo monitors, groups and a status page at `/s/demo`.

The [setup guide](/setup/) covers TLS, reverse proxies, plain Docker and Kubernetes.

## What this is, and what it is not

**Statora is** a self-hosted service for watching the things you run and telling people how they're doing. It checks your services from where you install it, keeps the history, and publishes status pages that you control. It also gives your automation a complete API.

**Statora is not** a metrics or APM platform. It doesn't scrape Prometheus, trace requests or store logs. It also doesn't check from many locations around the world on its own, though you can run more than one instance. If you need to know *whether* something works and *who should be told*, Statora is a good fit. If you need to know *why* it's slow, pair it with your observability stack.

</div>
