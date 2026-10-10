"""SAML 2.0 SP-initiated login using python3-saml (optional dependency: `statora[saml]`)."""

import asyncio
from typing import Any
from urllib.parse import urlsplit

from statora.config import get_settings
from statora.db.models import AuthProvider
from statora.schemas.auth_provider import SamlConfig

from .base import AuthError, ExternalIdentity, load_config

try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
    from onelogin.saml2.settings import OneLogin_Saml2_Settings

    SAML_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the native xmlsec library
    SAML_AVAILABLE = False

POST_BINDING = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"


def sp_urls(provider_id: int) -> dict[str, str]:
    base = get_settings().base_url.rstrip("/")
    prefix = f"{base}/auth/saml/{provider_id}"
    return {"metadata": f"{prefix}/metadata", "acs": f"{prefix}/acs", "login": f"{prefix}/login"}


def _require() -> None:
    if not SAML_AVAILABLE:
        raise AuthError("SAML support is not installed (pip install 'statora[saml]')")


def _idp_settings(cfg: SamlConfig) -> dict[str, Any]:
    if cfg.idp_metadata_xml:
        return OneLogin_Saml2_IdPMetadataParser.parse(cfg.idp_metadata_xml)["idp"]
    if cfg.idp_metadata_url:
        return OneLogin_Saml2_IdPMetadataParser.parse_remote(cfg.idp_metadata_url, timeout=10)["idp"]
    return {
        "entityId": cfg.idp_entity_id,
        "singleSignOnService": {
            "url": cfg.idp_sso_url,
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        },
        "x509cert": cfg.idp_x509_cert,
    }


def _settings(provider: AuthProvider, cfg: SamlConfig) -> dict[str, Any]:
    urls = sp_urls(provider.id)
    signing = bool(cfg.sp_private_key and cfg.sp_x509_cert)
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": cfg.sp_entity_id or urls["metadata"],
            "assertionConsumerService": {"url": urls["acs"], "binding": POST_BINDING},
            "NameIDFormat": cfg.name_id_format,
            "x509cert": cfg.sp_x509_cert or "",
            "privateKey": cfg.sp_private_key or "",
        },
        "idp": _idp_settings(cfg),
        "security": {
            "authnRequestsSigned": signing,
            "wantAssertionsSigned": cfg.want_assertions_signed,
            "wantMessagesSigned": False,
            "wantNameId": True,
            "requestedAuthnContext": False,
        },
    }


def _request_data(path: str, get: dict[str, str], post: dict[str, str]) -> dict[str, Any]:
    # Derive host/scheme from base_url so validation works behind a reverse proxy.
    base = urlsplit(get_settings().base_url)
    return {
        "https": "on" if base.scheme == "https" else "off",
        "http_host": base.hostname,
        "server_port": base.port or (443 if base.scheme == "https" else 80),
        "script_name": path,
        "get_data": get,
        "post_data": post,
    }


async def begin_login(provider: AuthProvider, relay_state: str) -> tuple[str, str]:
    """Returns the IdP redirect URL and the AuthnRequest ID to remember in the session."""
    _require()
    cfg: SamlConfig = load_config(provider)

    def _run() -> tuple[str, str]:
        settings = _settings(provider, cfg)
        auth = OneLogin_Saml2_Auth(_request_data(f"/auth/saml/{provider.id}/login", {}, {}), settings)
        url = auth.login(return_to=relay_state)
        return url, auth.get_last_request_id()

    try:
        return await asyncio.to_thread(_run)
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(f"SAML configuration error: {exc}") from exc


def _attr(attributes: dict[str, list[str]], name: str | None) -> str | None:
    if not name:
        return None
    values = attributes.get(name) or []
    return values[0] if values else None


async def complete_login(
    provider: AuthProvider, post_data: dict[str, str], request_id: str | None
) -> ExternalIdentity:
    _require()
    cfg: SamlConfig = load_config(provider)

    def _run() -> ExternalIdentity:
        auth = OneLogin_Saml2_Auth(
            _request_data(f"/auth/saml/{provider.id}/acs", {}, post_data), _settings(provider, cfg)
        )
        auth.process_response(request_id=request_id)
        if auth.get_errors() or not auth.is_authenticated():
            reason = auth.get_last_error_reason() or ", ".join(auth.get_errors())
            raise AuthError(f"SAML login failed: {reason}")
        attrs = auth.get_attributes()
        name_id = auth.get_nameid()
        return ExternalIdentity(
            external_id=name_id,
            username=_attr(attrs, cfg.username_attr) or name_id,
            email=_attr(attrs, cfg.email_attr),
            display_name=_attr(attrs, cfg.name_attr),
            groups=list(attrs.get(cfg.groups_attr or "", [])),
        )

    try:
        return await asyncio.to_thread(_run)
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(f"SAML response could not be processed: {exc}") from exc


async def metadata(provider: AuthProvider) -> str:
    _require()
    cfg: SamlConfig = load_config(provider)

    def _run() -> str:
        settings = OneLogin_Saml2_Settings(_settings(provider, cfg), sp_validation_only=True)
        xml = settings.get_sp_metadata()
        errors = settings.validate_metadata(xml)
        if errors:
            raise AuthError(f"Invalid SP metadata: {', '.join(errors)}")
        return xml.decode() if isinstance(xml, bytes) else xml

    return await asyncio.to_thread(_run)


async def test_connection(provider: AuthProvider) -> str:
    _require()
    cfg: SamlConfig = load_config(provider)
    try:
        idp = await asyncio.to_thread(_idp_settings, cfg)
    except Exception as exc:
        raise AuthError(f"Could not load IdP metadata: {exc}") from exc
    return f"IdP {idp.get('entityId')} loaded"
