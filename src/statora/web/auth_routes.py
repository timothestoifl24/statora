"""Browser login: local/LDAP form, OIDC and SAML single sign-on, logout."""

import json
import logging
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.auth import ratelimit
from statora.auth.providers import oidc, saml
from statora.auth.providers.base import AuthError
from statora.auth.service import authenticate_password, enabled_providers, provision_user
from statora.config import get_settings
from statora.db.models import AuthProvider, AuthProviderType
from statora.web.deps import get_session, login_user, not_found, optional_user, verify_csrf
from statora.web.templating import templates

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

RELAY_MAX_AGE = 600


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/admin"


def _relay_key(relay: str) -> str:
    return f"statora:saml:relay:{relay}"


async def _render_login(request: Request, session: AsyncSession, error: str | None = None, status: int = 200):
    providers = await enabled_providers(session)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "error": error,
            "next": _safe_next(request.query_params.get("next")),
            "show_password_form": not get_settings().disable_local_login
            or any(p.type == AuthProviderType.LDAP for p in providers),
            "sso_providers": [p for p in providers if p.type != AuthProviderType.LDAP],
            "has_ldap": any(p.type == AuthProviderType.LDAP for p in providers),
        },
        status_code=status,
    )


@router.get("/login")
async def login_page(
    request: Request, session: AsyncSession = Depends(get_session), user=Depends(optional_user)
):
    if user is not None:
        return RedirectResponse(_safe_next(request.query_params.get("next")), status_code=303)
    return await _render_login(request, session)


@router.post("/login", dependencies=[Depends(verify_csrf)])
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/admin"),
    session: AsyncSession = Depends(get_session),
):
    client_ip = request.client.host if request.client else "unknown"
    keys = (f"ip:{client_ip}", f"user:{username.strip().lower()}")
    if not await ratelimit.hit(*keys):
        return await _render_login(
            request, session, "Too many login attempts. Try again in a few minutes.", 429
        )
    try:
        user = await authenticate_password(session, username, password)
    except AuthError as exc:
        await session.commit()
        return await _render_login(request, session, str(exc), 401)
    await ratelimit.reset(keys[1])
    login_user(request, user)
    return RedirectResponse(_safe_next(next), status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


async def _provider(session: AsyncSession, provider_id: int, type_: AuthProviderType) -> AuthProvider:
    provider = await session.get(AuthProvider, provider_id)
    if provider is None or not provider.enabled or provider.type != type_:
        raise not_found("Login provider")
    return provider


# ---------------------------------------------------------------- OIDC / OAuth2


@router.get("/auth/oidc/{provider_id}/login")
async def oidc_login(provider_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    provider = await _provider(session, provider_id, AuthProviderType.OIDC)
    redirect_uri = f"{get_settings().base_url.rstrip('/')}/auth/oidc/{provider_id}/callback"
    try:
        url, flow = await oidc.begin_login(provider, redirect_uri)
    except Exception as exc:
        log.warning("OIDC login start failed for provider %s: %s", provider_id, exc)
        return await _render_login(request, session, f"{provider.name} is not reachable right now", 502)
    flow["next"] = _safe_next(request.query_params.get("next"))
    request.session[f"oidc:{provider_id}"] = flow
    return RedirectResponse(url, status_code=303)


@router.get("/auth/oidc/{provider_id}/callback")
async def oidc_callback(provider_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    provider = await _provider(session, provider_id, AuthProviderType.OIDC)
    flow = request.session.pop(f"oidc:{provider_id}", None)
    try:
        identity = await oidc.complete_login(provider, flow, dict(request.query_params))
        user = await provision_user(session, provider, identity)
    except AuthError as exc:
        return await _render_login(request, session, str(exc), 401)
    await session.commit()
    login_user(request, user)
    return RedirectResponse(_safe_next(flow.get("next") if flow else None), status_code=303)


# ---------------------------------------------------------------- SAML


@router.get("/auth/saml/{provider_id}/login")
async def saml_login(provider_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    provider = await _provider(session, provider_id, AuthProviderType.SAML)
    # The ACS request is a cross-site POST that doesn't carry our SameSite=Lax session cookie, so the
    # flow state lives in Redis under a one-time random RelayState.
    relay = secrets.token_urlsafe(32)
    try:
        url, request_id = await saml.begin_login(provider, relay_state=relay)
    except AuthError as exc:
        return await _render_login(request, session, str(exc), 502)
    state = {"rid": request_id, "next": _safe_next(request.query_params.get("next")), "pid": provider_id}
    await cache.set_json(_relay_key(relay), state, RELAY_MAX_AGE)
    return RedirectResponse(url, status_code=303)


@router.post("/auth/saml/{provider_id}/acs")
async def saml_acs(provider_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    provider = await _provider(session, provider_id, AuthProviderType.SAML)
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    relay = form.get("RelayState", "")
    state = await cache.get_redis().getdel(_relay_key(relay)) if relay else None
    if state is None:
        return await _render_login(request, session, "SAML login expired or was not started here", 400)
    state = json.loads(state)
    if state.get("pid") != provider_id:
        return await _render_login(request, session, "SAML response for a different provider", 400)
    try:
        identity = await saml.complete_login(provider, form, state.get("rid"))
        user = await provision_user(session, provider, identity)
    except AuthError as exc:
        return await _render_login(request, session, str(exc), 401)
    await session.commit()
    login_user(request, user)
    return RedirectResponse(_safe_next(state.get("next")), status_code=303)


@router.get("/auth/saml/{provider_id}/metadata")
async def saml_metadata(provider_id: int, session: AsyncSession = Depends(get_session)):
    provider = await session.get(AuthProvider, provider_id)
    if provider is None or provider.type != AuthProviderType.SAML:
        raise not_found("SAML provider")
    try:
        xml = await saml.metadata(provider)
    except AuthError as exc:
        return Response(str(exc), status_code=500, media_type="text/plain")
    return Response(xml, media_type="application/samlmetadata+xml")
