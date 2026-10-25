from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import UserRole
from statora.services import media
from statora.web.deps import ApiError, api_role, get_session

router = APIRouter(prefix="/media", tags=["media"])


class MediaRead(BaseModel):
    ref: str = Field(
        description='Use as a status page "favicon" or a monitor "icon"', examples=["media:3a7bd3e2…"]
    )
    url: str
    content_type: str
    size: int


@router.post("", response_model=MediaRead, status_code=201, dependencies=[Depends(api_role(UserRole.EDITOR))])
async def upload_media(file: UploadFile, session: AsyncSession = Depends(get_session)):
    """Upload a PNG, JPEG, WebP, GIF, ICO or SVG image (at most 256 KB, 2048 × 2048 px).

    Raster images are re-encoded as PNG (at most 256 px per side) and SVGs are rebuilt from an
    allowlist of shapes and attributes, so scripts and other embedded content are removed.
    Identical files are stored once.
    """
    data = await file.read(media.MAX_BYTES + 1)
    try:
        stored = await media.store(session, data)
    except media.MediaError as exc:
        raise ApiError(422, "invalid_file", exc.public_message) from exc
    await session.commit()
    return MediaRead(
        ref=media.ref(stored),
        url=media.url(media.ref(stored)),
        content_type=stored.content_type,
        size=stored.size,
    )
