from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import Media
from statora.web.deps import get_session, not_found

router = APIRouter(include_in_schema=False)

# Uploaded SVGs could carry markup; never let them run script or load anything, even if opened directly.
_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "Cross-Origin-Resource-Policy": "cross-origin",
}


@router.get("/media/{sha256}")
async def serve_media(sha256: str, session: AsyncSession = Depends(get_session)):
    media = await session.scalar(select(Media).where(Media.sha256 == sha256.lower()))
    if media is None:
        raise not_found("File")
    return Response(media.data, media_type=media.content_type, headers=_HEADERS)
