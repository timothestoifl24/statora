from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import User, UserRole
from statora.schemas.common import IconRef
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
        return JSONResponse({"detail": exc.public_message}, 422)
    await session.commit()
    ref = media.ref(stored)
    return {"ref": ref, "url": media.url(ref)}


_ICON_REF = TypeAdapter(IconRef)


@router.get("/media/preview")
async def preview_ref(ref: str = "", user: User = Depends(ui_role(UserRole.EDITOR))):
    """Image URL for a typed reference, after the same validation as saving it (icon picker preview)."""
    try:
        valid = _ICON_REF.validate_python(ref.strip() or None)
    except ValidationError:
        return {"src": None}
    return {"src": media.url(valid) if valid and not valid.startswith("fa:") else None}
