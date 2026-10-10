from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from statora.services.status import get_page_summary
from statora.web.deps import get_session, not_found

router = APIRouter(prefix="/public", tags=["public"])


@router.get(
    "/pages/{slug}/summary",
    summary="Public status page summary",
    description="No authentication. Same data as the public HTML page; cached for a few seconds.",
)
async def get_public_page_summary(slug: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    summary = await get_page_summary(session, slug)
    if summary is None:
        raise not_found("Status page")
    return summary
