"""User management, authentication providers and personal API tokens."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from statora.auth import passwords, tokens
from statora.auth.providers import base as provider_base
from statora.auth.providers.base import AuthError
from statora.auth.providers.saml import sp_urls
from statora.config import get_settings
from statora.db.base import utcnow
from statora.db.models import ApiToken, AuthProvider, AuthProviderType, TokenScope, User, UserRole
from statora.schemas.auth_provider import CONFIG_MODELS, SECRET_FIELDS, AuthProviderBase
from statora.schemas.users import UserCreate, UserUpdate
from statora.services.auth_providers import test_provider
from statora.web.deps import current_user, get_session, not_found, ui_role

from .common import checkbox, done, error_messages, flash, opt, redirect, render, render_form, rollback

router = APIRouter()
admin = ui_role(UserRole.ADMIN)
_MULTILINE_FIELDS = {"idp_metadata_xml", "idp_x509_cert", "sp_x509_cert", "sp_private_key"}


# ---------------------------------------------------------------- users


@router.get("/users")
async def list_users(
    request: Request, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    users = (
        await session.scalars(select(User).options(selectinload(User.auth_provider)).order_by(User.username))
    ).all()
    return render(request, "admin/users_list.html", user, users=users)


@router.get("/users/new")
async def new_user(request: Request, user: User = Depends(admin)):
    return render_form(
        request,
        "admin/user_form.html",
        user,
        target=None,
        values={"role": "viewer", "active": True},
        errors=[],
        roles=list(UserRole),
    )


@router.post("/users/new")
async def create_user(
    request: Request, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    values = {
        "username": str(form.get("username", "")).strip(),
        "email": opt(form.get("email")),
        "display_name": opt(form.get("display_name")),
        "password": form.get("password") or "",
        "role": form.get("role", "viewer"),
        "active": checkbox(form, "active"),
    }
    try:
        data = UserCreate.model_validate(values)
        if await session.scalar(select(User.id).where(func.lower(User.username) == data.username.lower())):
            raise ValueError(f"Username {data.username!r} is taken")
    except (ValidationError, ValueError) as exc:
        return render_form(
            request,
            "admin/user_form.html",
            user,
            422,
            target=None,
            values=values,
            errors=error_messages(exc),
            roles=list(UserRole),
        )
    session.add(
        User(**data.model_dump(exclude={"password"}), password_hash=passwords.hash_password(data.password))
    )
    await session.commit()
    flash(request, f"User {data.username} created")
    return done(request, "/admin/users")


async def _get_user(session: AsyncSession, user_id: int) -> User:
    target = await session.scalar(
        select(User).options(selectinload(User.auth_provider)).where(User.id == user_id)
    )
    if target is None:
        raise not_found("User")
    return target


@router.get("/users/{user_id}/edit")
async def edit_user(
    user_id: int, request: Request, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    target = await _get_user(session, user_id)
    values = {
        "username": target.username,
        "email": target.email,
        "display_name": target.display_name,
        "role": target.role,
        "active": target.active,
    }
    return render_form(
        request, "admin/user_form.html", user, target=target, values=values, errors=[], roles=list(UserRole)
    )


@router.post("/users/{user_id}/edit")
async def update_user(
    user_id: int, request: Request, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    target = await _get_user(session, user_id)
    form = await request.form()
    values = {
        "email": opt(form.get("email")),
        "display_name": opt(form.get("display_name")),
        "role": form.get("role", target.role),
        "active": checkbox(form, "active"),
    }
    if form.get("password"):
        values["password"] = form.get("password")
    try:
        data = UserUpdate.model_validate(values)
        if target.id == user.id and (not data.active or data.role != UserRole.ADMIN):
            raise ValueError("You can't demote or disable your own account")
        if data.password and not target.is_local:
            raise ValueError("Passwords of external users are managed by their identity provider")
    except (ValidationError, ValueError) as exc:
        return render_form(
            request,
            "admin/user_form.html",
            user,
            422,
            target=target,
            values={**values, "username": target.username},
            errors=error_messages(exc),
            roles=list(UserRole),
        )
    for field, value in data.model_dump(exclude={"password"}).items():
        setattr(target, field, value)
    if data.password:
        target.password_hash = passwords.hash_password(data.password)
    await session.commit()
    flash(request, "User saved")
    return done(request, "/admin/users")


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int, request: Request, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    target = await _get_user(session, user_id)
    if target.id == user.id:
        flash(request, "You can't delete your own account", "danger")
        return redirect("/admin/users")
    await session.delete(target)
    await session.commit()
    flash(request, f"User {target.username} deleted")
    return redirect("/admin/users")


# ---------------------------------------------------------------- auth providers


def _field_specs(provider_type: AuthProviderType) -> list[dict]:
    """Describe a provider's config fields so the template can render a generic form."""
    specs = []
    for name, field in CONFIG_MODELS[provider_type].model_fields.items():
        if "bool" in str(field.annotation):
            kind = "bool"
        elif name in _MULTILINE_FIELDS:
            kind = "textarea"
        else:
            kind = "text"
        specs.append(
            {
                "name": name,
                "label": name.replace("_", " ").capitalize(),
                "kind": kind,
                "secret": name in SECRET_FIELDS[provider_type],
                "required": field.is_required(),
                "default": "" if field.is_required() or field.default is None else field.default,
                "help": field.description,
            }
        )
    return specs


def _mapping_text(mapping: dict) -> str:
    return "\n".join(f"{group} = {role}" for group, role in (mapping or {}).items())


def _parse_mapping(text: str) -> dict[str, str]:
    mapping = {}
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        group, sep, role = line.rpartition("=")
        if not sep:
            raise ValueError(f"Group mapping line {line!r} must look like 'group = role'")
        mapping[group.strip()] = role.strip()
    return mapping


async def _provider_form(request, user, provider_type, provider=None, values=None, errors=None, status=200):
    if values is None:
        values = {
            "name": provider.name if provider else "",
            "enabled": provider.enabled if provider else True,
            "auto_create_users": provider.auto_create_users if provider else True,
            "default_role": provider.default_role if provider else "viewer",
            "button_label": (provider.button_label or "") if provider else "",
            "mapping": _mapping_text(provider.group_role_mapping) if provider else "",
            "config": provider_base.public_config(provider) if provider else {},
        }
    return render(
        request,
        "admin/auth_provider_form.html",
        user,
        status,
        provider=provider,
        provider_type=AuthProviderType(provider_type),
        values=values,
        errors=errors or [],
        fields=_field_specs(AuthProviderType(provider_type)),
        roles=list(UserRole),
        saml_urls=sp_urls(provider.id) if provider and provider.type == AuthProviderType.SAML else None,
        oidc_callback=f"{get_settings().base_url.rstrip('/')}/auth/oidc/{provider.id}/callback"
        if provider and provider.type == AuthProviderType.OIDC
        else None,
        stored_secrets={
            n
            for n in SECRET_FIELDS[AuthProviderType(provider_type)]
            if provider and provider_base.has_secret(provider, n)
        },
    )


def _provider_values_from_form(form, provider_type: AuthProviderType) -> dict:
    config = {}
    for spec in _field_specs(provider_type):
        key = f"cfg_{spec['name']}"
        if spec["kind"] == "bool":
            config[spec["name"]] = checkbox(form, key)
        else:
            value = opt(form.get(key))
            if value is not None:
                config[spec["name"]] = value
    return {
        "name": str(form.get("name", "")).strip(),
        "enabled": checkbox(form, "enabled"),
        "auto_create_users": checkbox(form, "auto_create_users"),
        "default_role": form.get("default_role", "viewer"),
        "button_label": opt(form.get("button_label")),
        "mapping": form.get("mapping", ""),
        "config": config,
    }


@router.get("/settings/auth")
async def list_providers(
    request: Request, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    providers = (await session.scalars(select(AuthProvider).order_by(AuthProvider.name))).all()
    counts = dict(
        (
            await session.execute(
                select(User.auth_provider_id, func.count())
                .where(User.auth_provider_id.is_not(None))
                .group_by(User.auth_provider_id)
            )
        ).all()
    )
    return render(
        request,
        "admin/auth_providers_list.html",
        user,
        providers=providers,
        counts=counts,
        types=list(AuthProviderType),
        local_disabled=get_settings().disable_local_login,
    )


@router.get("/settings/auth/new/{provider_type}")
async def new_provider(provider_type: AuthProviderType, request: Request, user: User = Depends(admin)):
    return await _provider_form(request, user, provider_type)


async def _save_provider(
    session, provider: AuthProvider | None, provider_type: AuthProviderType, values: dict
):
    base = AuthProviderBase.model_validate(
        {
            **{k: v for k, v in values.items() if k not in ("mapping", "config")},
            "group_role_mapping": _parse_mapping(values["mapping"]),
        }
    )
    query = select(AuthProvider.id).where(func.lower(AuthProvider.name) == base.name.lower())
    if provider:
        query = query.where(AuthProvider.id != provider.id)
    if await session.scalar(query):
        raise ValueError(f"Provider name {base.name!r} is taken")
    config = provider_base.store_config(
        provider_type, values["config"], provider.config if provider else None
    )
    if provider is None:
        provider = AuthProvider(type=provider_type)
        session.add(provider)
    for field, value in base.model_dump().items():
        setattr(provider, field, value)
    provider.config = config
    await session.flush()
    return provider


@router.post("/settings/auth/new/{provider_type}")
async def create_provider(
    provider_type: AuthProviderType,
    request: Request,
    user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    values = _provider_values_from_form(await request.form(), provider_type)
    try:
        provider = await _save_provider(session, None, provider_type, values)
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        return await _provider_form(request, user, provider_type, None, values, error_messages(exc), 422)
    await session.commit()
    flash(request, f"Provider “{provider.name}” created")
    return redirect(f"/admin/settings/auth/{provider.id}")


async def _get_provider(session: AsyncSession, provider_id: int) -> AuthProvider:
    provider = await session.get(AuthProvider, provider_id)
    if provider is None:
        raise not_found("Auth provider")
    return provider


@router.get("/settings/auth/{provider_id}")
async def edit_provider(
    provider_id: int,
    request: Request,
    user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    provider = await _get_provider(session, provider_id)
    return await _provider_form(request, user, provider.type, provider)


@router.post("/settings/auth/{provider_id}")
async def update_provider(
    provider_id: int,
    request: Request,
    user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    provider = await _get_provider(session, provider_id)
    values = _provider_values_from_form(await request.form(), provider.type)
    try:
        await _save_provider(session, provider, provider.type, values)
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        provider = await _get_provider(session, provider_id)
        return await _provider_form(request, user, provider.type, provider, values, error_messages(exc), 422)
    await session.commit()
    flash(request, "Provider saved")
    return redirect(f"/admin/settings/auth/{provider.id}")


@router.post("/settings/auth/{provider_id}/test")
async def test_provider_ui(
    provider_id: int,
    request: Request,
    user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    provider = await _get_provider(session, provider_id)
    try:
        message, ok = await test_provider(provider), True
    except AuthError as exc:
        message, ok = str(exc), False
    return render(request, "admin/_test_result.html", user, ok=ok, message=message)


@router.post("/settings/auth/{provider_id}/delete")
async def delete_provider(
    provider_id: int,
    request: Request,
    user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    provider = await _get_provider(session, provider_id)
    await session.delete(provider)
    await session.commit()
    flash(request, f"Provider “{provider.name}” deleted")
    return redirect("/admin/settings/auth")


# ---------------------------------------------------------------- personal API tokens


@router.get("/profile/tokens")
async def list_tokens(
    request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    items = (
        await session.scalars(
            select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.id.desc())
        )
    ).all()
    new_token = request.session.pop("new_token", None)
    return render(
        request,
        "admin/tokens.html",
        user,
        tokens=items,
        new_token=new_token,
        now=utcnow(),
        base_url=get_settings().base_url.rstrip("/"),
    )


@router.post("/profile/tokens")
async def create_token(
    request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    name = str(form.get("name", "")).strip()[:100] or "token"
    scopes = [TokenScope.READ] + ([TokenScope.WRITE] if checkbox(form, "write") else [])
    days = str(form.get("expires_days", "")).strip()
    expires_at = utcnow() + timedelta(days=int(days)) if days.isdigit() and int(days) > 0 else None
    issued = await tokens.issue_token(session, user, name, scopes, expires_at)
    await session.commit()
    # Shown exactly once on the next page load.
    request.session["new_token"] = issued.plaintext
    return redirect("/admin/profile/tokens")


@router.post("/profile/tokens/{token_id}/revoke")
async def revoke_token(
    token_id: int,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    token = await session.get(ApiToken, token_id)
    if token is not None and token.user_id == user.id:
        await tokens.revoke_token(session, token)
        await session.commit()
        flash(request, f"Token “{token.name}” revoked")
    return redirect("/admin/profile/tokens")
