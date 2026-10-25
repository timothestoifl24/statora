"""Uploaded images (favicons, monitor icons), stored in the database and addressed by content hash."""

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import Media

MAX_BYTES = 256 * 1024
MEDIA_REF = re.compile(r"^media:([0-9a-f]{64})$")

# Magic bytes of the raster formats we accept; SVG is checked separately.
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
)
# Anything that can run script or pull in other documents. Uploaded SVGs are also served with a
# sandboxing Content-Security-Policy, so this is a second line of defence.
_SVG_FORBIDDEN = re.compile(
    rb"<\s*script|<\s*foreignobject|<!doctype|<!entity|\bon[a-z]+\s*=|javascript:|data:text/html|<\s*iframe|<\s*embed|<\s*object",
    re.IGNORECASE,
)


class MediaError(ValueError):
    pass


def sniff(data: bytes) -> str:
    """Content type from the file's bytes; the declared type and file name are not trusted."""
    for magic, content_type in _SIGNATURES:
        if data.startswith(magic):
            return content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:1024].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg"):
        if b"<svg" not in data[:4096].lower():
            raise MediaError("This XML file is not an SVG image")
        if _SVG_FORBIDDEN.search(data):
            raise MediaError("SVG files must not contain scripts, event handlers or embedded documents")
        return "image/svg+xml"
    raise MediaError("Upload a PNG, JPEG, WebP, GIF, ICO or SVG image")


async def store(session: AsyncSession, data: bytes) -> Media:
    if not data:
        raise MediaError("The file is empty")
    if len(data) > MAX_BYTES:
        raise MediaError(f"Images can be at most {MAX_BYTES // 1024} KB")
    content_type = sniff(data)
    digest = hashlib.sha256(data).hexdigest()
    media = await session.scalar(select(Media).where(Media.sha256 == digest))
    if media is None:
        media = Media(sha256=digest, content_type=content_type, size=len(data), data=data)
        session.add(media)
        await session.flush()
    return media


def ref(media: Media) -> str:
    return f"media:{media.sha256}"


def url(reference: str | None) -> str | None:
    """Browser URL for a stored image reference ("media:<sha256>" or an http(s) URL)."""
    if not reference:
        return None
    if match := MEDIA_REF.match(reference):
        return f"/media/{match.group(1)}"
    if reference.startswith(("https://", "http://")):
        return reference
    return None
