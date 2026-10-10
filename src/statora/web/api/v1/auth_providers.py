from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.auth.providers import base as provider_base
from statora.auth.providers.base import AuthError
from statora.db.models import AuthProvider, UserRole
from statora.schemas.auth_provider import AuthProviderCreate, AuthProviderRead, AuthProviderUpdate
from statora.schemas.common import Page
from statora.services.auth_providers import test_provider
from statora.web.deps import ApiError, api_role, get_session, not_found

router = APIRouter(
    prefix="/auth-providers", tags=["auth-providers"], dependencies=[Depends(api_role(UserRole.ADMIN))]
)


class TestResult(BaseModel):
    ok: bool
    message: str


def _read(provider: AuthProvider) -> AuthProviderRead:
    data = AuthProviderRead.model_validate(provider)
    data.config = provider_base.public_config(provider)
    return data


async def _get(session: AsyncSession, provider_id: int) -> AuthProvider:
    provider = await session.get(AuthProvider, provider_id)
    if provider is None:
        raise not_found("Auth provider")
    return provider


async def _name_taken(session: AsyncSession, name: str, exclude: int | None = None) -> bool:
    query = select(AuthProvider.id).where(func.lower(AuthProvider.name) == name.lower())
    if exclude:
        query = query.where(AuthProvider.id != exclude)
    return bool(await session.scalar(query))


@router.get("", response_model=Page[AuthProviderRead])
async def list_auth_providers(session: AsyncSession = Depends(get_session)):
    items = (await session.scalars(select(AuthProvider).order_by(AuthProvider.id))).all()
    return Page(items=[_read(p) for p in items], total=len(items), limit=len(items), offset=0)


@router.post("", response_model=AuthProviderRead, status_code=201)
async def create_auth_provider(data: AuthProviderCreate, session: AsyncSession = Depends(get_session)):
    if await _name_taken(session, data.name):
        raise ApiError(409, "conflict", f"Provider name {data.name!r} is taken")
    provider = AuthProvider(
        **data.model_dump(exclude={"config"}), config=provider_base.store_config(data.type, data.config)
    )
    session.add(provider)
    await session.commit()
    return _read(provider)


@router.get("/{provider_id}", response_model=AuthProviderRead)
async def get_auth_provider(provider_id: int, session: AsyncSession = Depends(get_session)):
    return _read(await _get(session, provider_id))


@router.patch("/{provider_id}", response_model=AuthProviderRead)
async def update_auth_provider(
    provider_id: int, data: AuthProviderUpdate, session: AsyncSession = Depends(get_session)
):
    provider = await _get(session, provider_id)
    changes = data.model_dump(exclude_unset=True, exclude={"config"})
    if "name" in changes and await _name_taken(session, changes["name"], provider.id):
        raise ApiError(409, "conflict", f"Provider name {changes['name']!r} is taken")
    for field, value in changes.items():
        setattr(provider, field, value)
    if data.config is not None:
        provider.config = provider_base.store_config(provider.type, data.config, provider.config)
    await session.commit()
    return _read(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_auth_provider(provider_id: int, session: AsyncSession = Depends(get_session)):
    provider = await session.get(AuthProvider, provider_id)
    if provider is not None:
        await session.delete(provider)
        await session.commit()
    return Response(status_code=204)


@router.post("/{provider_id}/test", response_model=TestResult, summary="Check connectivity to the IdP")
async def test_auth_provider(provider_id: int, session: AsyncSession = Depends(get_session)):
    try:
        message = await test_provider(await _get(session, provider_id))
    except AuthError as exc:
        return TestResult(ok=False, message=str(exc))
    return TestResult(ok=True, message=message)
