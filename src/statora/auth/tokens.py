"""API tokens: `st_<prefix>_<secret>`. Only a SHA-256 hash of the full token is stored."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from statora import cache
from statora.db.base import utcnow
from statora.db.models import ApiToken, TokenScope, User

TOKEN_PREFIX = "st_"
CACHE_TTL = 60
LAST_USED_RESOLUTION = timedelta(minutes=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class IssuedToken:
    token: ApiToken
    plaintext: str


async def issue_token(
    session: AsyncSession,
    user: User,
    name: str,
    scopes: list[TokenScope],
    expires_at: datetime | None = None,
) -> IssuedToken:
    prefix = secrets.token_hex(4)
    plaintext = f"{TOKEN_PREFIX}{prefix}_{secrets.token_urlsafe(32)}"
    token = ApiToken(
        user_id=user.id,
        name=name,
        token_prefix=prefix,
        token_hash=hash_token(plaintext),
        scopes=sorted({TokenScope(s) for s in scopes}),
        expires_at=expires_at,
    )
    session.add(token)
    await session.flush()
    return IssuedToken(token, plaintext)


async def revoke_token(session: AsyncSession, token: ApiToken) -> None:
    await cache.get_redis().delete(cache.token_key(token.token_hash))
    await session.delete(token)


async def authenticate_token(session: AsyncSession, plaintext: str) -> tuple[User, ApiToken] | None:
    if not plaintext.startswith(TOKEN_PREFIX):
        return None
    token_hash = hash_token(plaintext)
    key = cache.token_key(token_hash)

    cached = await cache.get_json(key)
    if cached == "invalid":
        return None
    token = await session.scalar(
        select(ApiToken).where(ApiToken.token_hash == token_hash).options(selectinload(ApiToken.user))
    )
    now = utcnow()
    if token is None or not token.user.active or (token.expires_at and token.expires_at <= now):
        await cache.set_json(key, "invalid", CACHE_TTL)
        return None

    if token.last_used_at is None or now - token.last_used_at > LAST_USED_RESOLUTION:
        token.last_used_at = now
    return token.user, token
