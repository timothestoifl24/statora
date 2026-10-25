from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import User, UserRole
from statora.services import media
from statora.web.deps import get_session, ui_role

router = APIRouter()


@router.post("/media")
async def upload_media(
    request: Request,
    user: User = Depends(ui_role(UserRole.EDITOR)),
    session: AsyncSession = Depends(get_session),
):
    """Image upload for the favicon and monitor icon fields; the form then stores the returned ref."""
    form = await request.form()
    upload = form.get("file")
    if upload is None or isinstance(upload, str):
        return JSONResponse({"detail": "Choose an image to upload"}, 422)
    data = await upload.read(media.MAX_BYTES + 1)
    try:
        stored = await media.store(session, data)
    except media.MediaError as exc:
        return JSONResponse({"detail": str(exc)}, 422)
    await session.commit()
    ref = media.ref(stored)
    return {"ref": ref, "url": media.url(ref)}
