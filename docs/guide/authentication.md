# Users & sign-in

## Local accounts

Admins create local users under **Users**, with a role: viewer, editor or admin. Passwords are hashed with Argon2. Login attempts are rate-limited per IP address and per username (10 attempts per 5 minutes by default).

### The initial admin

A fresh instance has no users, so instead of the sign-in page the first visit asks you to create the admin account. This *initial admin* is a local admin that can't be deleted, disabled or demoted, so there is always a way in, even when your identity provider is down. Other admins can still change its email, display name and password.

If you lose its password, reset it from the command line. This also re-enables the account and restores the admin role:

```bash
statora reset-admin                    # prompts for the new password
statora reset-admin --username root    # and renames the account
```

Instances set up before 1.2.0 with `statora create-admin` treat their oldest local admin as the initial admin. If such an instance has no local admin left, for example because only identity-provider admins remain, `statora reset-admin` makes the local account `admin` the initial admin, creating it if needed; pass `--username` to pick another local account.

### Hiding the local sign-in form

Once people sign in through an identity provider, you can hide the username and password form under **Authentication → Local accounts** ("Show the local sign-in form"). The sign-in page then only shows the provider buttons.

- It can only be hidden while at least one provider is enabled. If the last provider is disabled or deleted, the form comes back by itself.
- While an LDAP provider is enabled the form stays, because LDAP accounts sign in with it.
- Hiding the form doesn't turn local accounts off. `/login?local=1` always shows the form, for example when the identity provider is down. To stop non-admin local accounts from signing in at all, use `STATORA_DISABLE_LOCAL_LOGIN`.

## External identity providers

Add providers under **Authentication → Add provider**. Each provider has:

- **Create users on first login**: just-in-time provisioning with a default role.
- **Group → role mapping**: one `group = role` per line. The highest matching role wins, and roles are refreshed at every login. Without a mapping, roles are managed by hand in the admin panel.
- **Test connection**: checks the LDAP bind, OIDC discovery or SAML metadata without signing anyone in.

Secrets (bind passwords, client secrets, private keys) are encrypted in the database with a key derived from `STATORA_SECRET_KEY`, and never shown again after saving.

### LDAP / Active Directory

Users sign in with the normal username/password form, which tries local accounts first, then each LDAP provider. Two modes:

- **Search and bind**: a service account (`bind_dn`, `bind_password`) searches `user_search_base` with `user_filter`, for example `(uid={username})` or, for AD, `(sAMAccountName={username})`. Statora then binds as the user that was found.
- **Direct bind**: `bind_dn_template`, for example `uid={username},ou=people,dc=example,dc=org`.

Groups come from `memberOf`, or from a search when `group_search_base` and `group_filter` are set. LDAPS and StartTLS are supported. Input is escaped, and empty passwords are rejected, so anonymous binds can't log anyone in.

### OAuth2 / OpenID Connect

Works with Keycloak, Microsoft Entra ID, Google, Authentik, Okta, GitHub and other providers.

- Give the **discovery URL** (`…/.well-known/openid-configuration`) for OIDC, or the authorize, token and userinfo URLs for plain OAuth2.
- Register the **redirect URL** shown on the provider page: `STATORA_BASE_URL/auth/oidc/<id>/callback`.
- **Claims** for username, email, name and groups are configurable, including nested ones such as `realm_access.roles`.

Statora uses the authorization-code flow with PKCE, state and nonce, and validates ID tokens against the provider's published keys.

### SAML 2.0

- Give the IdP **metadata URL** or XML, or the entity ID, SSO URL and certificate.
- Configure your IdP with the **ACS URL** and **SP metadata** shown on the provider page (`STATORA_BASE_URL/auth/saml/<id>/acs` and `/metadata`).
- Map the username, email, name and groups attributes. Optionally add an SP certificate and key to sign requests.

Responses must be signed (assertions by default), and each login can only be completed once.

::: tip Locked out?
Local admins can always use the password form at `/login?local=1`, even with `STATORA_DISABLE_LOCAL_LOGIN=true` or with the form hidden, so a broken identity provider can't lock everyone out.
:::
