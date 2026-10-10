import os
import socket
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import respx
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from sqlalchemy import select

from statora.auth.providers import ldap, oidc, saml
from statora.auth.providers.base import AuthError, ExternalIdentity, store_config
from statora.auth.service import authenticate_password, provision_user
from statora.db.models import AuthProvider, AuthProviderType, User, UserRole

from .conftest import needs_services

pytestmark = needs_services

ISSUER = "https://idp.test/realms/main"


async def _provider(session, type_: AuthProviderType, config: dict, **kw) -> AuthProvider:
    provider = AuthProvider(
        name=f"{type_}-{len(config)}", type=type_, config=store_config(type_, config), **kw
    )
    session.add(provider)
    await session.commit()
    return provider


# ---------------------------------------------------------------- provisioning


async def test_jit_provisioning_and_role_sync(session):
    provider = await _provider(
        session,
        AuthProviderType.OIDC,
        {"discovery_url": f"{ISSUER}/.well-known/openid-configuration", "client_id": "sp"},
        group_role_mapping={"ops": "editor", "admins": "admin"},
    )
    identity = ExternalIdentity("sub-1", "jane", "jane@example.org", "Jane", ["ops"])
    user = await provision_user(session, provider, identity)
    assert (user.username, user.role, user.email) == ("jane", UserRole.EDITOR, "jane@example.org")

    identity.groups = ["admins"]
    again = await provision_user(session, provider, identity)
    assert again.id == user.id and again.role == UserRole.ADMIN

    # A different provider's "jane" gets a unique username instead of taking over the account.
    other = await _provider(
        session, AuthProviderType.OIDC, {"discovery_url": "https://o/x", "client_id": "a", "scopes": "openid"}
    )
    clash = await provision_user(session, other, ExternalIdentity("sub-9", "jane"))
    assert clash.username == "jane-2" and clash.role == UserRole.VIEWER


async def test_provisioning_disabled_and_disabled_users(session):
    provider = await _provider(
        session,
        AuthProviderType.OIDC,
        {"discovery_url": "https://o/x", "client_id": "a"},
        auto_create_users=False,
    )
    with pytest.raises(AuthError, match="not registered"):
        await provision_user(session, provider, ExternalIdentity("s", "nobody"))

    session.add(User(username="known", auth_provider_id=provider.id, external_id="k", active=False))
    await session.commit()
    with pytest.raises(AuthError, match="disabled"):
        await provision_user(session, provider, ExternalIdentity("k", "known"))


# ---------------------------------------------------------------- OIDC


def _mock_metadata(key: RSAKey):
    respx.get(f"{ISSUER}/.well-known/openid-configuration").respond(
        json={
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/auth",
            "token_endpoint": f"{ISSUER}/token",
            "userinfo_endpoint": f"{ISSUER}/userinfo",
            "jwks_uri": f"{ISSUER}/certs",
        }
    )
    respx.get(f"{ISSUER}/certs").respond(json=KeySet([key]).as_dict(private=False))


def _mock_tokens(key: RSAKey, claims: dict, userinfo: dict | None = None):
    id_token = jwt.encode({"alg": "RS256", "kid": key.kid}, claims, KeySet([key]))
    token_route = respx.post(f"{ISSUER}/token").respond(json={"access_token": "at", "id_token": id_token})
    respx.get(f"{ISSUER}/userinfo").respond(json=userinfo or {"sub": claims["sub"]})
    return token_route


@respx.mock
async def test_oidc_login_flow(session):
    provider = await _provider(
        session,
        AuthProviderType.OIDC,
        {
            "discovery_url": f"{ISSUER}/.well-known/openid-configuration",
            "client_id": "statora",
            "client_secret": "s3cret",
            "groups_claim": "realm_access.roles",
        },
        group_role_mapping={"sp-admin": "admin"},
    )
    key = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    _mock_metadata(key)

    url, flow = await oidc.begin_login(provider, "http://testserver/auth/oidc/1/callback")
    params = parse_qs(urlsplit(url).query)
    assert params["code_challenge_method"] == ["S256"] and params["state"] == [flow["state"]]

    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": "statora",
        "sub": "u-42",
        "nonce": flow["nonce"],
        "iat": now,
        "exp": now + 300,
        "preferred_username": "kim",
        "email": "kim@example.org",
        "realm_access": {"roles": ["sp-admin"]},
    }
    token_route = _mock_tokens(key, claims)

    identity = await oidc.complete_login(provider, flow, {"state": flow["state"], "code": "abc"})
    assert (identity.external_id, identity.username, identity.groups) == ("u-42", "kim", ["sp-admin"])
    sent = parse_qs(token_route.calls.last.request.content.decode())
    assert sent["code_verifier"] == [flow["verifier"]] and sent["client_secret"] == ["s3cret"]

    user = await provision_user(session, provider, identity)
    assert user.role == UserRole.ADMIN


@respx.mock
async def test_oidc_rejects_bad_state_nonce_and_audience(session):
    provider = await _provider(
        session,
        AuthProviderType.OIDC,
        {
            "discovery_url": f"{ISSUER}/.well-known/openid-configuration",
            "client_id": "statora",
        },
    )
    key = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    _mock_metadata(key)
    _, flow = await oidc.begin_login(provider, "http://testserver/cb")
    now = int(time.time())
    base = {
        "iss": ISSUER,
        "aud": "statora",
        "sub": "u",
        "nonce": flow["nonce"],
        "iat": now,
        "exp": now + 300,
    }

    with pytest.raises(AuthError, match="state"):
        await oidc.complete_login(provider, flow, {"state": "forged", "code": "x"})
    with pytest.raises(AuthError, match="Identity provider error"):
        await oidc.complete_login(provider, flow, {"error": "access_denied"})

    token_route = _mock_tokens(key, {**base, "nonce": "replayed"})
    with pytest.raises(AuthError, match="Invalid ID token"):
        await oidc.complete_login(provider, flow, {"state": flow["state"], "code": "x"})

    token_route.respond(
        json={
            "access_token": "at",
            "id_token": jwt.encode(
                {"alg": "RS256", "kid": "k1"}, {**base, "aud": "someone-else"}, KeySet([key])
            ),
        }
    )
    with pytest.raises(AuthError, match="Invalid ID token"):
        await oidc.complete_login(provider, flow, {"state": flow["state"], "code": "x"})


async def test_oidc_login_route_redirects_and_stores_flow(client, session):
    provider = await _provider(
        session,
        AuthProviderType.OIDC,
        {
            "authorize_url": "https://gh.test/authorize",
            "token_url": "https://gh.test/token",
            "userinfo_url": "https://gh.test/user",
            "client_id": "gh",
            "scopes": "read:user",
        },
    )
    response = await client.get(f"/auth/oidc/{provider.id}/login?next=/admin/pages")
    assert response.status_code == 303 and response.headers["location"].startswith(
        "https://gh.test/authorize?"
    )
    login_page = await client.get("/login")
    assert f"/auth/oidc/{provider.id}/login" in login_page.text


# ---------------------------------------------------------------- SAML

IDP_CERT = """MIICmzCCAYMCBgGLvR8q0zANBgkqhkiG9w0BAQsFADARMQ8wDQYDVQQDDAZtYXN0ZXIwHhcNMjMxMTIwMTAwMDAwWhcNMzMx
MTIwMTAwMTQwWjARMQ8wDQYDVQQDDAZtYXN0ZXIwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC7"""


@pytest.mark.skipif(not saml.SAML_AVAILABLE, reason="python3-saml not installed")
async def test_saml_metadata_login_redirect_and_acs_guard(client, session):
    provider = await _provider(
        session,
        AuthProviderType.SAML,
        {
            "idp_entity_id": "https://idp.test/saml",
            "idp_sso_url": "https://idp.test/sso",
            "idp_x509_cert": IDP_CERT,
            "groups_attr": "memberOf",
        },
    )
    metadata = await client.get(f"/auth/saml/{provider.id}/metadata")
    assert metadata.status_code == 200, metadata.text
    assert "http://statora.test/auth/saml/1/acs" in metadata.text and "EntityDescriptor" in metadata.text

    login = await client.get(f"/auth/saml/{provider.id}/login")
    assert login.status_code == 303
    location = urlsplit(login.headers["location"])
    assert location.netloc == "idp.test" and "SAMLRequest" in parse_qs(location.query)

    # An ACS post without a RelayState we issued is rejected before any XML is parsed.
    forged = await client.post(
        f"/auth/saml/{provider.id}/acs", data={"SAMLResponse": "x", "RelayState": "nope"}
    )
    assert forged.status_code == 400

    relay = parse_qs(location.query)["RelayState"][0]
    garbage = await client.post(
        f"/auth/saml/{provider.id}/acs", data={"SAMLResponse": "bm90IHhtbA==", "RelayState": relay}
    )
    assert garbage.status_code == 401
    # RelayState is single-use.
    replay = await client.post(
        f"/auth/saml/{provider.id}/acs", data={"SAMLResponse": "x", "RelayState": relay}
    )
    assert replay.status_code == 400


# ---------------------------------------------------------------- LDAP (needs the "sso" compose profile)

LDAP_URL = os.environ.get("STATORA_TEST_LDAP_URL", "ldap://localhost:1389")


def _ldap_up() -> bool:
    parts = urlsplit(LDAP_URL)
    try:
        with socket.create_connection((parts.hostname, parts.port or 389), timeout=1):
            return True
    except OSError:
        return False


ldap_only = pytest.mark.skipif(
    not _ldap_up(), reason="OpenLDAP test server not running (compose profile 'sso')"
)

LDAP_SEARCH = {
    "server_uri": LDAP_URL,
    "bind_dn": "cn=admin,dc=example,dc=org",
    "bind_password": "adminpassword",
    "user_search_base": "ou=users,dc=example,dc=org",
    "user_filter": "(uid={username})",
    "group_search_base": "ou=groups,dc=example,dc=org",
    "group_filter": "(member={user_dn})",
}


@ldap_only
async def test_ldap_search_bind_with_groups(session):
    provider = await _provider(
        session, AuthProviderType.LDAP, LDAP_SEARCH, group_role_mapping={"statora-admins": "admin"}
    )
    identity = await ldap.authenticate(provider, "alice", "alicepassword")
    assert identity.external_id == "cn=alice,ou=users,dc=example,dc=org"
    assert identity.username == "alice" and "statora-admins" in identity.groups
    assert "Connected and bound" in await ldap.test_connection(provider)

    with pytest.raises(AuthError):
        await ldap.authenticate(provider, "alice", "wrong")
    with pytest.raises(AuthError):
        await ldap.authenticate(provider, "alice", "")  # no unauthenticated binds
    with pytest.raises(AuthError):
        await ldap.authenticate(provider, "*", "alicepassword")  # filter injection


@ldap_only
async def test_ldap_direct_bind_and_password_login(session):
    await _provider(
        session,
        AuthProviderType.LDAP,
        {
            "server_uri": LDAP_URL,
            "bind_dn_template": "cn={username},ou=users,dc=example,dc=org",
        },
        default_role=UserRole.EDITOR,
    )
    user = await authenticate_password(session, "bob", "bobpassword")
    await session.commit()
    assert user.auth_provider_id is not None and user.role == UserRole.EDITOR
    assert await session.scalar(
        select(User.username).where(User.external_id == "cn=bob,ou=users,dc=example,dc=org")
    )


@ldap_only
async def test_api_token_with_ldap_credentials(client, session):
    await _provider(
        session, AuthProviderType.LDAP, LDAP_SEARCH, group_role_mapping={"statora-admins": "admin"}
    )
    response = await client.post(
        "/api/v1/auth/token", json={"username": "alice", "password": "alicepassword"}
    )
    assert response.status_code == 201, response.text
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {response.json()['token']}"})
    assert me.json()["role"] == "admin" and me.json()["auth_provider_id"] is not None
