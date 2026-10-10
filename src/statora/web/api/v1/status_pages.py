from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.db.models import StatusPage
from statora.schemas.common import Page
from statora.schemas.pages import StatusPageCreate, StatusPageRead, StatusPageUpdate
from statora.services import crud
from statora.web.deps import get_session, not_found, write_role

router = APIRouter(prefix="/status-pages", tags=["status-pages"], dependencies=[Depends(write_role())])


async def _get(session: AsyncSession, page_id: int) -> StatusPage:
    page = await session.scalar(crud.page_query().where(StatusPage.id == page_id))
    if page is None:
        raise not_found("Status page")
    return page


@router.get("", response_model=Page[StatusPageRead])
async def list_status_pages(
    session: AsyncSession = Depends(get_session),
    slug: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = crud.page_query()
    if slug is not None:
        query = query.where(StatusPage.slug == slug)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    items = (await session.scalars(query.order_by(StatusPage.id).limit(limit).offset(offset))).all()
    return Page(items=items, total=total or 0, limit=limit, offset=offset)


@router.post("", response_model=StatusPageRead, status_code=201)
async def create_status_page(data: StatusPageCreate, session: AsyncSession = Depends(get_session)):
    page = await crud.create_page(session, data)
    await session.commit()
    return await _get(session, page.id)


@router.get("/{page_id}", response_model=StatusPageRead)
async def get_status_page(page_id: int, session: AsyncSession = Depends(get_session)):
    return await _get(session, page_id)


@router.patch("/{page_id}", response_model=StatusPageRead)
async def update_status_page(
    page_id: int, data: StatusPageUpdate, session: AsyncSession = Depends(get_session)
):
    await crud.update_page(session, await _get(session, page_id), data)
    await session.commit()
    session.expunge_all()
    return await _get(session, page_id)


@router.put("/{page_id}", response_model=StatusPageRead)
async def replace_status_page(
    page_id: int, data: StatusPageCreate, session: AsyncSession = Depends(get_session)
):
    await crud.update_page(session, await _get(session, page_id), StatusPageUpdate(**data.model_dump()))
    await session.commit()
    session.expunge_all()
    return await _get(session, page_id)


@router.delete("/{page_id}", status_code=204)
async def delete_status_page(page_id: int, session: AsyncSession = Depends(get_session)):
    page = await session.get(StatusPage, page_id)
    if page is not None:
        await session.delete(page)
        await session.commit()
        await cache.invalidate_pages()
    return Response(status_code=204)
