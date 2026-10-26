import re

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import Media
from statora.web.deps import get_session, not_found

router = APIRouter(include_in_schema=False)
_SHA256 = re.compile(r"[0-9a-f]{64}")

# Uploaded SVGs could carry markup; never let them run script or load anything, even if opened directly.
_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "Cross-Origin-Resource-Policy": "cross-origin",
}


@router.get("/media/{sha256}")
async def serve_media(sha256: str, session: AsyncSession = Depends(get_session)):
    if not _SHA256.fullmatch(sha256):
        raise not_found("File")  # never send arbitrary path text (or NUL bytes) to the database
    media = await session.scalar(select(Media).where(Media.sha256 == sha256))
    if media is None:
        raise not_found("File")
    return Response(media.data, media_type=media.content_type, headers=_HEADERS)


class UploadSizeLimit:
    """Reject upload requests over the limit before the body is read or spooled to disk.

    Checks Content-Length up front and counts the bytes of chunked bodies as they arrive.
    """

    def __init__(self, app, paths: tuple[str, ...], max_bytes: int) -> None:
        self.app, self.paths, self.max_bytes = app, paths, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.paths:
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
            return await _too_large(send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await _too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send) -> None:
    body = b'{"detail":"The upload is too large.","code":"payload_too_large"}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
