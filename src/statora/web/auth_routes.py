"""Browser login: local/LDAP form, OIDC and SAML single sign-on, logout."""

import json
import logging
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.auth import passwords, ratelimit
from statora.auth.providers import oidc, saml
from statora.auth.providers.base import AuthError
from statora.auth.service import (
    authenticate_password,
    enabled_providers,
    local_form_hidden,
    needs_setup,
    provision_user,
)
from statora.config import get_settings
from statora.db.models import AuthProvider, AuthProviderType, User, UserRole
from statora.schemas.users import UserCreate
from statora.web.admin.common import error_messages
from statora.web.deps import get_session, local_path, login_user, not_found, optional_user, verify_csrf
from statora.web.templating import templates

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

RELAY_MAX_AGE = 600


def _relay_key(relay: str) -> str:
    return f"statora:saml:relay:{relay}"


async def _render_login(request: Request, session: AsyncSession, error: str | None = None, status: int = 200):
    providers = await enabled_providers(session)
    has_ldap = any(p.type == AuthProviderType.LDAP for p in providers)
    # /login?local=1 always shows the form: the way back in when the identity provider is down.
    forced = request.query_params.get("local") == "1"
    hidden = not forced and await local_form_hidden(session, providers)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "error": error,
            "next": local_path(request.query_params.get("next")),
            "show_password_form": not hidden
            and (not get_settings().disable_local_login or has_ldap or forced),
            "sso_providers": [p for p in providers if p.type != AuthProviderType.LDAP],
            "has_ldap": has_ldap,
            "local_forced": forced,
        },
        status_code=status,
    )


@router.get("/login")
async def login_page(
    request: Request, session: AsyncSession = Depends(get_session), user=Depends(optional_user)
):
    if user is not None:
        return RedirectResponse(local_path(request.query_params.get("next")), status_code=303)
    if await needs_setup(session):
        return RedirectResponse("/setup", status_code=303)
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
    return RedirectResponse(local_path(next), status_code=303)


# ---------------------------------------------------------------- first-run setup


def _render_setup(request: Request, values: dict, errors: list[str] | None = None, status: int = 200):
    return templates.TemplateResponse(
        request, "auth/setup.html", {"values": values, "errors": errors or []}, status_code=status
    )


@router.get("/setup")
async def setup_page(request: Request, session: AsyncSession = Depends(get_session)):
    if not await needs_setup(session):
        return RedirectResponse("/login", status_code=303)
    return _render_setup(request, {"username": "admin"})


@router.post("/setup", dependencies=[Depends(verify_csrf)])
async def setup_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if not await needs_setup(session):
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    values = {
        "username": str(form.get("username", "")).strip(),
        "email": str(form.get("email", "")).strip() or None,
        "display_name": str(form.get("display_name", "")).strip() or None,
        "password": str(form.get("password", "")),
        "role": UserRole.ADMIN,
    }
    try:
        data = UserCreate.model_validate(values)
        if data.password != form.get("password_confirm"):
            raise ValueError("The passwords don't match")
    except (ValidationError, ValueError) as exc:
        return _render_setup(request, values, error_messages(exc), 422)
    user = User(
        **data.model_dump(exclude={"password"}),
        password_hash=passwords.hash_password(data.password),
        is_initial_admin=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Someone else finished the setup a moment earlier.
        await session.rollback()
        return RedirectResponse("/login", status_code=303)
    login_user(request, user)
    return RedirectResponse("/admin", status_code=303)


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
    flow["next"] = local_path(request.query_params.get("next"))
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
    return RedirectResponse(local_path(flow.get("next") if flow else None), status_code=303)


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
    state = {"rid": request_id, "next": local_path(request.query_params.get("next")), "pid": provider_id}
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
    return RedirectResponse(local_path(state.get("next")), status_code=303)


@router.get("/auth/saml/{provider_id}/metadata")
async def saml_metadata(provider_id: int, session: AsyncSession = Depends(get_session)):
    provider = await session.get(AuthProvider, provider_id)
    if provider is None or provider.type != AuthProviderType.SAML:
        raise not_found("SAML provider")
    try:
        xml = await saml.metadata(provider)
    except AuthError as exc:
        # The reason can name keys or certificate details, so it goes to the log, not the response.
        log.warning("SAML metadata failed for provider %s: %s", provider_id, exc)
        return Response("SAML metadata is not available", status_code=500, media_type="text/plain")
    return Response(xml, media_type="application/samlmetadata+xml")
