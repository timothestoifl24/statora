import hashlib
import logging
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.auth import tokens
from statora.config import get_settings
from statora.db.models import ApiToken, TokenScope, User, UserRole
from statora.db.session import sessionmaker

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

log = logging.getLogger(__name__)


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def local_path(target: str | None, default: str = "/admin") -> str:
    """Return target if it is a path on this site, else default; guards every redirect.

    Browsers drop tabs and newlines and read backslashes as slashes, so a path with either can
    still leave the site; anything with a scheme or host is refused too.
    """
    if not target or "\\" in target or any(ch.isspace() or not ch.isprintable() for ch in target):
        return default
    # A no-op after the check above, but stripping backslashes and then testing urlparse() on the
    # same value is the shape CodeQL's open-redirect query recognises as a sanitizer.
    target = target.replace("\\", "")
    if not target.startswith("/") or target.startswith("//"):
        return default
    if not urlparse(target).netloc and not urlparse(target).scheme:
        return target
    return default


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------- UI (session cookie)


class LoginRequired(Exception):
    """Raised for anonymous UI requests; handled by redirecting to /login."""


# The session cookie is signed, not stored on the server; each login also gets a record in Redis so
# that logging out can end a session before the cookie expires. The record carries a fingerprint
# of the password hash the login was checked against, and every request compares it with the
# database: a password change ends all older sessions, even one created by a login that raced it,
# and even if Redis was unreachable when the change was saved.


def _session_key(sid: str) -> str:
    return f"statora:session:{sid}"


def _user_sessions_key(user_id: int) -> str:
    return f"statora:user-sessions:{user_id}"


def _session_record(user: User) -> str:
    fingerprint = hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:24]
    return f"{user.id}:{fingerprint}"


async def login_user(request: Request, user: User) -> None:
    request.session.clear()
    sid = secrets.token_urlsafe(32)
    ttl = get_settings().session_max_age
    now = time.time()
    sessions = _user_sessions_key(user.id)
    async with cache.get_redis().pipeline(transaction=True) as pipe:
        pipe.set(_session_key(sid), _session_record(user), ex=ttl)
        # The user's session ids, scored by expiry so that expired ones are dropped as they go.
        pipe.zadd(sessions, {sid: now + ttl})
        pipe.zremrangebyscore(sessions, "-inf", now)
        pipe.expire(sessions, ttl)
        await pipe.execute()
    request.session["sid"] = sid
    request.session["uid"] = user.id
    request.session["csrf"] = secrets.token_urlsafe(32)


async def refresh_session(request: Request, user: User) -> None:
    """Keep the current session valid after the user changed their own password."""
    sid = request.session.get("sid")
    if isinstance(sid, str):
        await cache.get_redis().set(_session_key(sid), _session_record(user), keepttl=True, xx=True)


async def logout_user(request: Request) -> None:
    sid, uid = request.session.get("sid"), request.session.get("uid")
    try:
        if isinstance(sid, str):
            redis = cache.get_redis()
            await redis.delete(_session_key(sid))
            if isinstance(uid, int):
                await redis.zrem(_user_sessions_key(uid), sid)
    except Exception:
        log.exception("Could not end session on the server; it expires on its own")
    finally:
        # The browser forgets the session whatever happened above.
        request.session.clear()


async def end_user_sessions(user_id: int, keep: Request | None = None) -> None:
    """Delete the records of a user's sessions, e.g. after a password change; `keep`: the request
    whose session stays (someone changing their own password). Best effort: the password
    fingerprint already rejects those sessions, so a Redis error is logged, not raised."""
    kept = keep.session.get("sid") if keep is not None else None
    try:
        redis = cache.get_redis()
        sessions = _user_sessions_key(user_id)
        sids = [sid for sid in await redis.zrange(sessions, 0, -1) if sid != kept]
        if sids:
            await redis.delete(*(_session_key(sid) for sid in sids))
            await redis.zrem(sessions, *sids)
    except Exception:
        log.exception("Could not delete the session records of user %s", user_id)


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(32)
    return token


async def optional_user(request: Request, session: AsyncSession = Depends(get_session)) -> User | None:
    uid = request.session.get("uid")
    if uid is None:
        return None
    sid = request.session.get("sid")
    record = await cache.get_redis().get(_session_key(sid)) if isinstance(sid, str) else None
    user = await session.get(User, uid) if record is not None else None
    if user is None or not user.active or record != _session_record(user):
        # Logged out, expired, password changed since, the user is gone or disabled, or a cookie
        # from before sessions were recorded.
        request.session.clear()
        return None
    return user


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise LoginRequired
    return user


def ui_role(role: UserRole):
    async def dependency(user: User = Depends(current_user)) -> User:
        if not user.has_role(role):
            raise HTTPException(403, "You don't have permission to do that")
        return user

    return dependency


async def verify_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    expected = request.session.get("csrf")
    sent = request.headers.get("X-CSRF-Token")
    if sent is None:
        form = await request.form()
        sent = form.get("csrf_token")
    if not expected or not isinstance(sent, str) or not secrets.compare_digest(expected, sent):
        raise HTTPException(403, "Invalid or missing CSRF token; reload the page and try again")


# ---------------------------------------------------------------- API (bearer token)

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="ApiToken",
    description="API token (`st_…`) from the UI (Profile → API tokens) or `POST /api/v1/auth/token`.",
)


@dataclass
class Principal:
    user: User
    token: ApiToken


async def api_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if credentials is None:
        raise ApiError(401, "unauthenticated", "Missing bearer token")
    found = await tokens.authenticate_token(session, credentials.credentials)
    if found is None:
        raise ApiError(401, "invalid_token", "Invalid, expired or revoked token")
    user, token = found
    if request.method not in SAFE_METHODS and TokenScope.WRITE not in token.scopes:
        raise ApiError(403, "insufficient_scope", "This token is read-only (needs the 'write' scope)")
    return Principal(user, token)


def api_role(role: UserRole):
    async def dependency(principal: Principal = Depends(api_principal)) -> Principal:
        if not principal.user.has_role(role):
            raise ApiError(403, "forbidden", f"Requires the '{role}' role")
        return principal

    return dependency


def write_role(read: UserRole = UserRole.VIEWER, write: UserRole = UserRole.EDITOR):
    """Viewers may read, editors (by default) may change."""

    async def dependency(request: Request, principal: Principal = Depends(api_principal)) -> Principal:
        needed = read if request.method in SAFE_METHODS else write
        if not principal.user.has_role(needed):
            raise ApiError(403, "forbidden", f"Requires the '{needed}' role")
        return principal

    return dependency
