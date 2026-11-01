# Security policy

Statora handles credentials (LDAP bind passwords, OIDC client secrets, SAML keys, API tokens) and is often reachable from the internet, so security reports get priority.

## Supported versions

| Version | Security fixes |
|---|---|
| 0.x | The latest 0.x release only. Please upgrade before reporting. |

From 1.0 on, the latest minor release is supported, and the previous minor release keeps getting security fixes for 3 months after a new one comes out.

## Reporting a vulnerability

**Please don't report security problems in public issues, discussions or pull requests.**

Report them privately through GitHub:

1. Go to [**Security → Report a vulnerability**](https://github.com/timothestoifl24/statora/security/advisories/new).
2. Describe the problem. Helpful details:
   - the Statora version, and how it runs (Docker, Compose, Kubernetes, source);
   - which part is affected (for example the API, a sign-in method, status pages, the container image);
   - steps to reproduce, or a proof of concept;
   - what an attacker could achieve, and what access they need first.

If you can't use GitHub, email [security@timothestoifl24.dev](mailto:security@timothestoifl24.dev) instead.

The report is visible only to you and the maintainers. We can discuss it, work on a fix in a private fork, and publish an advisory, all in the same place.

## What happens next

| Step | Target |
|---|---|
| Acknowledgement | within 3 business days |
| First assessment (confirmed or not, severity) | within 7 days |
| Fix released, critical or high severity | within 30 days |
| Fix released, medium or low severity | within 90 days |

We'll keep you informed along the way. Once a fix is released, we publish a GitHub Security Advisory, request a CVE where appropriate, and credit you, unless you'd rather stay anonymous. If no fix is possible within 90 days, we agree on a disclosure date with you.

## Scope

**In scope:**

- the Statora application: admin panel, public status pages, REST API, scheduler and checks;
- authentication and sessions: local accounts, LDAP, OIDC, SAML, API tokens, CSRF protection, rate limiting;
- storage of secrets (encrypted provider configuration, token hashes);
- the official container image (`docker.io/timothestoifl24/statora`), `docker-compose.yml` and the Kubernetes manifests in `deploy/kubernetes`.

**Out of scope:**

- vulnerabilities in dependencies that Statora doesn't make exploitable. Please report those to the dependency's project; tell us if Statora is affected and we'll update;
- problems that require an already compromised host, database or admin account;
- insecure configurations explicitly warned against in the documentation, such as running without HTTPS or using a weak `STATORA_SECRET_KEY`;
- denial of service by sheer traffic volume, and missing rate limits on endpoints that don't handle credentials;
- reports from automated scanners without a demonstrated impact, and social engineering.

## Safe harbour

We won't take legal action against good-faith research that:
- stays within your own installation;
- avoids harming other people's data or services;
- gives us reasonable time to fix the problem before disclosure.

## Running Statora securely

- Serve it over HTTPS and set `STATORA_SECURE_COOKIES=true`.
- Use a long random `STATORA_SECRET_KEY` and keep it secret. It signs sessions and encrypts stored identity-provider secrets.
- Run the container as shipped: non-root, and ideally with a read-only root filesystem and no capabilities. See [Docker hardening](https://statora.timothestoifl24.dev/setup/docker#hardening).
- Give API tokens the smallest scope and role they need, and set an expiry.
- Keep Statora, PostgreSQL and Redis up to date, and don't expose PostgreSQL or Redis to the internet.
