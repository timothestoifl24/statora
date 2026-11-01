from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.auth import passwords, ratelimit, tokens
from statora.auth.providers.base import AuthError
from statora.auth.service import authenticate_password
from statora.db.base import utcnow
from statora.db.models import ApiToken, User, UserRole
from statora.schemas.common import Page
from statora.schemas.users import (
    TokenCreate,
    TokenIssued,
    TokenRead,
    TokenRequest,
    UserCreate,
    UserRead,
    UserUpdate,
)
from statora.web.deps import ApiError, Principal, api_principal, api_role, get_session, not_found

auth = APIRouter(prefix="/auth", tags=["auth"])
users = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(api_role(UserRole.ADMIN))])
me = APIRouter(tags=["tokens"])


def _expiry(expires_in: int | None):
    return utcnow() + timedelta(seconds=expires_in) if expires_in else None


def _issued(issued: tokens.IssuedToken) -> TokenIssued:
    return TokenIssued(**TokenRead.model_validate(issued.token).model_dump(), token=issued.plaintext)


@auth.post(
    "/token",
    response_model=TokenIssued,
    status_code=201,
    summary="Create an API token from username and password",
    description="Works for local and LDAP accounts. SAML/OIDC users create tokens in the web UI.",
)
async def create_token_with_credentials(
    data: TokenRequest, request: Request, session: AsyncSession = Depends(get_session)
):
    client_ip = request.client.host if request.client else "unknown"
    keys = (f"ip:{client_ip}", f"user:{data.username.strip().lower()}")
    if not await ratelimit.hit(*keys):
        raise ApiError(429, "rate_limited", "Too many login attempts; try again later")
    try:
        user = await authenticate_password(session, data.username, data.password)
    except AuthError as exc:
        await session.commit()
        raise ApiError(401, "invalid_credentials", str(exc)) from exc
    await ratelimit.reset(keys[1])
    issued = await tokens.issue_token(session, user, data.name, data.scopes, _expiry(data.expires_in))
    await session.commit()
    return _issued(issued)


@me.get("/me", response_model=UserRead, tags=["users"])
async def get_current_user(principal: Principal = Depends(api_principal)):
    return principal.user


@me.get("/tokens", response_model=list[TokenRead])
async def list_tokens(
    principal: Principal = Depends(api_principal), session: AsyncSession = Depends(get_session)
):
    query = select(ApiToken).where(ApiToken.user_id == principal.user.id).order_by(ApiToken.id)
    return (await session.scalars(query)).all()


@me.post("/tokens", response_model=TokenIssued, status_code=201)
async def create_token(
    data: TokenCreate,
    principal: Principal = Depends(api_principal),
    session: AsyncSession = Depends(get_session),
):
    issued = await tokens.issue_token(
        session, principal.user, data.name, data.scopes, _expiry(data.expires_in)
    )
    await session.commit()
    return _issued(issued)


@me.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: int, principal: Principal = Depends(api_principal), session: AsyncSession = Depends(get_session)
):
    token = await session.get(ApiToken, token_id)
    if token is not None and token.user_id == principal.user.id:
        await tokens.revoke_token(session, token)
        await session.commit()
    return Response(status_code=204)


async def _get_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise not_found("User")
    return user


@users.get("", response_model=Page[UserRead])
async def list_users(
    session: AsyncSession = Depends(get_session),
    username: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = select(User)
    if username is not None:
        query = query.where(func.lower(User.username) == username.lower())
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    items = (await session.scalars(query.order_by(User.id).limit(limit).offset(offset))).all()
    return Page(items=items, total=total or 0, limit=limit, offset=offset)


@users.post("", response_model=UserRead, status_code=201, summary="Create a local user")
async def create_user(data: UserCreate, session: AsyncSession = Depends(get_session)):
    if await session.scalar(select(User.id).where(func.lower(User.username) == data.username.lower())):
        raise ApiError(409, "conflict", f"Username {data.username!r} is taken")
    user = User(**data.model_dump(exclude={"password"}), password_hash=passwords.hash_password(data.password))
    session.add(user)
    await session.commit()
    return user


@users.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_user(session, user_id)


@users.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    data: UserUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(api_principal),
):
    user = await _get_user(session, user_id)
    changes = data.model_dump(exclude_unset=True)
    if user.id == principal.user.id and (
        changes.get("active") is False or changes.get("role", "admin") != "admin"
    ):
        raise ApiError(400, "self_lockout", "You can't demote or disable your own account")
    if user.is_initial_admin and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise ApiError(400, "initial_admin", "The initial admin can't be demoted or disabled")
    if "password" in changes:
        if not user.is_local:
            raise ApiError(400, "external_user", "Passwords of external users are managed by their provider")
        user.password_hash = passwords.hash_password(changes.pop("password"))
    for field, value in changes.items():
        setattr(user, field, value)
    await session.commit()
    return user


@users.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int, session: AsyncSession = Depends(get_session), principal: Principal = Depends(api_principal)
):
    if user_id == principal.user.id:
        raise ApiError(400, "self_lockout", "You can't delete your own account")
    user = await session.get(User, user_id)
    if user is not None and user.is_initial_admin:
        raise ApiError(400, "initial_admin", "The initial admin can't be deleted")
    if user is not None:
        await session.delete(user)
        await session.commit()
    return Response(status_code=204)
