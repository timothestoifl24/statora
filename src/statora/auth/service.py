"""User authentication and provisioning of users from external identity providers."""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.config import get_settings
from statora.db.base import utcnow
from statora.db.models import AuthProvider, AuthProviderType, User, UserRole
from statora.services import app_settings

from . import passwords
from .providers import ldap
from .providers.base import AuthError, ExternalIdentity


def role_for_groups(provider: AuthProvider, groups: list[str]) -> UserRole:
    """Highest role among matching groups (case-insensitive), else the provider's default role."""
    mapping = {key.lower(): UserRole(value) for key, value in (provider.group_role_mapping or {}).items()}
    matched = [mapping[g.lower()] for g in groups if g.lower() in mapping]
    if not matched:
        return UserRole(provider.default_role)
    return max(matched, key=lambda role: role.level)


async def _unique_username(session: AsyncSession, wanted: str) -> str:
    base = re.sub(r"\s+", ".", wanted.strip())[:140] or "user"
    candidate, n = base, 1
    while await session.scalar(select(User.id).where(func.lower(User.username) == candidate.lower())):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def provision_user(session: AsyncSession, provider: AuthProvider, identity: ExternalIdentity) -> User:
    user = await session.scalar(
        select(User).where(User.auth_provider_id == provider.id, User.external_id == identity.external_id)
    )
    if user is None:
        if not provider.auto_create_users:
            raise AuthError("Your account is not registered here; ask an administrator to create it")
        user = User(
            username=await _unique_username(session, identity.username),
            auth_provider_id=provider.id,
            external_id=identity.external_id,
            active=True,
        )
        session.add(user)
    if not user.active:
        raise AuthError("Your account is disabled")

    user.email = identity.email or user.email
    user.display_name = identity.display_name or user.display_name
    # Without a mapping the role is managed manually in the admin panel, so don't overwrite it.
    if provider.group_role_mapping or user.id is None:
        user.role = role_for_groups(provider, identity.groups)
    user.last_login_at = utcnow()
    await session.flush()
    return user


async def authenticate_local(session: AsyncSession, username: str, password: str) -> User | None:
    user = await session.scalar(
        select(User).where(
            func.lower(User.username) == username.strip().lower(), User.auth_provider_id.is_(None)
        )
    )
    if not passwords.verify_password(password, user.password_hash if user else None):
        return None
    assert user is not None
    if not user.active:
        return None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    user.last_login_at = utcnow()
    return user


async def enabled_providers(
    session: AsyncSession, type_: AuthProviderType | None = None
) -> list[AuthProvider]:
    query = select(AuthProvider).where(AuthProvider.enabled).order_by(AuthProvider.name)
    if type_:
        query = query.where(AuthProvider.type == type_)
    return list((await session.scalars(query)).all())


async def local_form_hidden(session: AsyncSession, providers: list[AuthProvider]) -> bool:
    """The admin chose to hide the local sign-in form, and there is another way to sign in.

    Without an enabled provider the form always shows, so nobody gets locked out. LDAP accounts
    sign in through the same form, so it also stays while an LDAP provider is enabled.
    """
    if not providers or any(p.type == AuthProviderType.LDAP for p in providers):
        return False
    return bool(await app_settings.get(session, app_settings.HIDE_LOCAL_LOGIN, False))


async def authenticate_password(session: AsyncSession, username: str, password: str) -> User:
    """Username/password login against local accounts, then each enabled LDAP provider."""
    if not get_settings().disable_local_login or await _is_local_admin(session, username):
        user = await authenticate_local(session, username, password)
        if user:
            return user
    for provider in await enabled_providers(session, AuthProviderType.LDAP):
        try:
            identity = await ldap.authenticate(provider, username, password)
        except AuthError:
            continue
        return await provision_user(session, provider, identity)
    raise AuthError("Invalid username or password")


async def _is_local_admin(session: AsyncSession, username: str) -> bool:
    # Local admins can always log in so a broken IdP can't lock everybody out.
    return bool(
        await session.scalar(
            select(User.id).where(
                func.lower(User.username) == username.strip().lower(),
                User.auth_provider_id.is_(None),
                User.role == UserRole.ADMIN,
            )
        )
    )
