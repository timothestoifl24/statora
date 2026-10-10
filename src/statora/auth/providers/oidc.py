"""OpenID Connect / OAuth2 authorization-code flow with PKCE."""

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from statora.db.models import AuthProvider
from statora.schemas.auth_provider import OidcConfig

from .base import AuthError, ExternalIdentity, load_config

HTTP_TIMEOUT = 10


async def _get_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()


async def discover(cfg: OidcConfig) -> dict[str, Any]:
    if cfg.discovery_url:
        meta = await _get_json(cfg.discovery_url)
    else:
        meta = {}
    return {
        "issuer": meta.get("issuer"),
        "authorization_endpoint": cfg.authorize_url or meta.get("authorization_endpoint"),
        "token_endpoint": cfg.token_url or meta.get("token_endpoint"),
        "userinfo_endpoint": cfg.userinfo_url or meta.get("userinfo_endpoint"),
        "jwks_uri": meta.get("jwks_uri"),
    }


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def begin_login(provider: AuthProvider, redirect_uri: str) -> tuple[str, dict[str, str]]:
    """Returns the IdP redirect URL and the state to keep in the user's session."""
    cfg: OidcConfig = load_config(provider)
    meta = await discover(cfg)
    flow = {
        "state": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(24),
        "verifier": secrets.token_urlsafe(48),
        "redirect_uri": redirect_uri,
    }
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": redirect_uri,
        "scope": cfg.scopes,
        "state": flow["state"],
        "nonce": flow["nonce"],
        "code_challenge": _pkce_challenge(flow["verifier"]),
        "code_challenge_method": "S256",
    }
    return f"{meta['authorization_endpoint']}?{urlencode(params)}", flow


def _claim(claims: dict[str, Any], name: str | None) -> Any:
    """Supports dotted paths for nested claims, e.g. 'realm_access.roles'."""
    if not name:
        return None
    value: Any = claims
    for part in name.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


async def _validate_id_token(id_token: str, meta: dict, cfg: OidcConfig, nonce: str) -> dict[str, Any]:
    if not meta.get("jwks_uri"):
        raise AuthError("IdP returned an ID token but publishes no JWKS")
    keys = KeySet.import_key_set(await _get_json(meta["jwks_uri"]))
    try:
        token = jwt.decode(id_token, keys)
        registry = jwt.JWTClaimsRegistry(
            iss={"essential": True, "value": meta["issuer"]},
            aud={"essential": True, "value": cfg.client_id},
            nonce={"essential": True, "value": nonce},
            sub={"essential": True},
        )
        registry.validate(token.claims)
    except (JoseError, ValueError) as exc:
        raise AuthError(f"Invalid ID token: {exc}") from exc
    return dict(token.claims)


async def complete_login(
    provider: AuthProvider, flow: dict[str, str] | None, params: dict[str, str]
) -> ExternalIdentity:
    if "error" in params:
        raise AuthError(f"Identity provider error: {params.get('error_description') or params['error']}")
    if not flow or not secrets.compare_digest(params.get("state", ""), flow["state"]):
        raise AuthError("Login session expired or state mismatch; please try again")
    if not params.get("code"):
        raise AuthError("Missing authorization code")

    cfg: OidcConfig = load_config(provider)
    meta = await discover(cfg)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.post(
            meta["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": params["code"],
                "redirect_uri": flow["redirect_uri"],
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret or "",
                "code_verifier": flow["verifier"],
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise AuthError(f"Token exchange failed ({response.status_code})")
        tokens = response.json()

        claims: dict[str, Any] = {}
        if tokens.get("id_token"):
            claims = await _validate_id_token(tokens["id_token"], meta, cfg, flow["nonce"])
        if meta.get("userinfo_endpoint") and tokens.get("access_token"):
            info = await client.get(
                meta["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {tokens['access_token']}", "Accept": "application/json"},
            )
            if info.status_code < 400:
                userinfo = info.json()
                if claims and userinfo.get("sub") not in (None, claims.get("sub")):
                    raise AuthError("Userinfo subject does not match ID token")
                claims = {**userinfo, **claims}
    if not claims:
        raise AuthError("Identity provider returned no user information")

    subject = claims.get("sub") or claims.get("id")
    username = _claim(claims, cfg.username_claim) or claims.get("login") or claims.get("email") or subject
    if subject is None or username is None:
        raise AuthError("Identity provider did not return a subject or username")
    groups = _claim(claims, cfg.groups_claim) or []
    if isinstance(groups, str):
        groups = [groups]
    return ExternalIdentity(
        external_id=str(subject),
        username=str(username),
        email=_claim(claims, cfg.email_claim),
        display_name=_claim(claims, cfg.name_claim),
        groups=[str(g) for g in groups],
    )


async def test_connection(provider: AuthProvider) -> str:
    cfg: OidcConfig = load_config(provider)
    try:
        meta = await discover(cfg)
    except httpx.HTTPError as exc:
        raise AuthError(f"Discovery failed: {exc}") from exc
    if not meta["authorization_endpoint"] or not meta["token_endpoint"]:
        raise AuthError("Discovery document lacks authorization or token endpoint")
    return f"Discovered issuer {meta['issuer'] or '(OAuth2, no issuer)'}"
