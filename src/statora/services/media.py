"""Uploaded images (favicons, monitor icons), stored in the database and addressed by content hash.

Nothing is stored as uploaded. Raster images are decoded and re-encoded as a fresh PNG, so data
hidden in the file (scripts, polyglot HTML/ZIP payloads, metadata) is gone. SVGs are parsed and
rebuilt from an allowlist of shapes and presentation attributes. Served files also carry a
sandboxing Content-Security-Policy (web/media.py) as a second line of defence.
"""

import hashlib
import io
import re
import warnings
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import Media

MAX_BYTES = 256 * 1024
MAX_SIDE = 2048  # largest accepted input image, in pixels per side (checked before decoding)
STORED_SIDE = 256  # raster images are scaled down to fit this; icons and favicons never need more
MAX_SVG_ELEMENTS = 5000
MEDIA_REF = re.compile(r"^media:([0-9a-f]{64})$")


class MediaError(ValueError):
    """A rejected upload. Only the fixed message for its code ever reaches the user."""

    MESSAGES = {
        "empty": "The file is empty.",
        "too_large": f"Images can be at most {MAX_BYTES // 1024} KB.",
        "unsupported": "Upload a PNG, JPEG, WebP, GIF, ICO or SVG image.",
        "corrupt": "This image is damaged or not what its type says, and can't be read.",
        "dimensions": f"Images can be at most {MAX_SIDE} × {MAX_SIDE} pixels.",
        "svg_invalid": "This SVG file isn't valid XML.",
        "svg_unsafe": "SVG files can't contain a DOCTYPE or entities.",
        "svg_empty": "Nothing drawable is left in this SVG after removing unsupported content.",
    }

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(self.MESSAGES[code])

    @property
    def public_message(self) -> str:
        return self.MESSAGES[self.code]


# ---------------------------------------------------------------- type detection

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"GIF87a", "GIF"),
    (b"GIF89a", "GIF"),
    (b"\x00\x00\x01\x00", "ICO"),
)


def sniff(data: bytes) -> str:
    """Format from the file's bytes; the declared type and file name are never trusted."""
    for magic, fmt in _SIGNATURES:
        if data.startswith(magic):
            return fmt
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or head.startswith(b"<!--"):
        return "SVG"
    raise MediaError("unsupported")


# ---------------------------------------------------------------- raster images


def _clean_raster(data: bytes, fmt: str) -> bytes:
    """Decode with the one decoder matching the detected format, then re-encode as PNG."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[fmt]) as probe:
                if max(probe.size) > MAX_SIDE:
                    raise MediaError("dimensions")
                probe.verify()
            with Image.open(io.BytesIO(data), formats=[fmt]) as img:
                if fmt == "ICO":
                    img.size = max(img.ico.sizes(), key=lambda s: s[0] * s[1])
                if max(img.size) > MAX_SIDE:
                    raise MediaError("dimensions")
                img.seek(0)  # first frame of an animation
                img.load()
                clean = ImageOps.exif_transpose(img).convert("RGBA")
        clean.thumbnail((STORED_SIDE, STORED_SIDE))
        out = io.BytesIO()
        clean.save(out, "PNG", optimize=True)  # no text chunks, no EXIF, nothing but pixels
        return out.getvalue()
    except MediaError:
        raise
    except Exception as exc:  # any decoder failure means we don't store it
        raise MediaError("corrupt") from exc


# ---------------------------------------------------------------- SVG

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)

_SVG_TAGS = {
    "svg", "g", "defs", "symbol", "use", "title", "desc",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "linearGradient", "radialGradient", "stop", "clipPath", "mask",
}  # fmt: skip
# Presentation and geometry attributes only: nothing that runs code or loads another resource.
_SVG_ATTRS = {
    "id", "viewBox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "fx", "fy", "d", "points", "transform", "preserveAspectRatio", "version", "offset",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity",
    "color", "display", "visibility", "stop-color", "stop-opacity", "clip-path", "clip-rule", "mask",
    "gradientUnits", "gradientTransform", "spreadMethod", "clipPathUnits", "maskUnits",
    "maskContentUnits", "font-family", "font-size", "font-weight", "font-style", "text-anchor",
    "dominant-baseline", "letter-spacing", "href",
}  # fmt: skip
_LOCAL_REF = re.compile(r"^#[A-Za-z_][\w.-]*$")
_URL_FUNC = re.compile(r"url\(\s*([^)]*?)\s*\)", re.IGNORECASE)
_SAFE_URL_FUNC = re.compile(r"^['\"]?#[A-Za-z_][\w.-]*['\"]?$")
_FORBIDDEN_VALUE = re.compile(r"javascript:|vbscript:|data:|expression\s*\(|@import|[<>\\]", re.IGNORECASE)


def _safe_value(name: str, value: str) -> str | None:
    value = "".join(ch for ch in value if ch >= " " or ch == "\t").strip()
    if len(value) > 20_000:
        return None
    if name == "href":
        return value if _LOCAL_REF.match(value) else None
    compact = re.sub(r"\s+", "", value)
    if _FORBIDDEN_VALUE.search(compact):
        return None
    if any(not _SAFE_URL_FUNC.match(m.group(1)) for m in _URL_FUNC.finditer(value)):
        return None  # url() may only point inside this file, e.g. fill="url(#gradient)"
    return value


def _local(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return None, tag


def _copy(src: ET.Element, count: list[int]) -> ET.Element | None:
    ns, name = _local(src.tag) if isinstance(src.tag, str) else (None, "")
    if ns not in (SVG_NS, None) or name not in _SVG_TAGS:
        return None  # drops script, style, foreignObject, image, a, animate, set, metadata, …
    count[0] += 1
    if count[0] > MAX_SVG_ELEMENTS:
        raise MediaError("svg_invalid")
    dst = ET.Element(f"{{{SVG_NS}}}{name}")
    attrs: dict[str, str] = {}
    for key, value in src.attrib.items():
        attr_ns, attr = _local(key)
        if attr_ns == XLINK_NS and attr == "href":
            attr_ns = None  # xlink:href becomes the SVG 2 href
        if attr_ns is not None:
            continue
        if attr == "style":  # keep allowed declarations as attributes; drop the rest
            for decl in value.split(";"):
                prop, _, val = decl.partition(":")
                prop = prop.strip().lower()
                if prop in _SVG_ATTRS and prop != "href" and (safe := _safe_value(prop, val)) is not None:
                    attrs.setdefault(prop, safe)
            continue
        if attr in _SVG_ATTRS and (safe := _safe_value(attr, value)) is not None:
            attrs[attr] = safe
    dst.attrib.update(attrs)
    if name in ("title", "desc", "text", "tspan") and src.text:
        dst.text = src.text[:2000]
    for child in src:
        if (copied := _copy(child, count)) is not None:
            copied.tail = child.tail if name in ("text", "tspan") and child.tail else None
            dst.append(copied)
    return dst


def _clean_svg(data: bytes) -> bytes:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MediaError("svg_invalid") from exc
    if re.search(r"<!\s*(doctype|entity)", text, re.IGNORECASE):
        raise MediaError("svg_unsafe")  # no external entities, no "billion laughs"
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise MediaError("svg_invalid") from exc
    if _local(root.tag) != (SVG_NS, "svg") and _local(root.tag) != (None, "svg"):
        raise MediaError("svg_invalid")
    clean = _copy(root, [0])
    if clean is None or not any(
        _local(el.tag)[1] not in ("svg", "title", "desc", "defs") for el in clean.iter()
    ):
        raise MediaError("svg_empty")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(clean, encoding="unicode").encode()


# ---------------------------------------------------------------- storage


def sanitize(data: bytes) -> tuple[bytes, str]:
    """Validate an upload and return the cleaned file and its content type."""
    if not data:
        raise MediaError("empty")
    if len(data) > MAX_BYTES:
        raise MediaError("too_large")
    fmt = sniff(data)
    if fmt == "SVG":
        return _clean_svg(data), "image/svg+xml"
    return _clean_raster(data, fmt), "image/png"


async def store(session: AsyncSession, data: bytes) -> Media:
    clean, content_type = sanitize(data)
    digest = hashlib.sha256(clean).hexdigest()
    media = await session.scalar(select(Media).where(Media.sha256 == digest))
    if media is None:
        media = Media(sha256=digest, content_type=content_type, size=len(clean), data=clean)
        session.add(media)
        await session.flush()
    return media


def ref(media: Media) -> str:
    return f"media:{media.sha256}"


def url(reference: str | None) -> str | None:
    """Browser URL for a stored image reference ("media:<sha256>" or an https URL); None otherwise."""
    if not reference:
        return None
    if match := MEDIA_REF.match(reference):
        return f"/media/{match.group(1)}"
    if reference.startswith("https://"):
        return reference
    return None
