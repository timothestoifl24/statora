from typing import Annotated, Generic, TypeVar
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field

from statora.services import icons

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str
    code: str = Field(description="Machine-readable error code, e.g. 'not_found'")


class Pagination(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


def _known_icon(value: str | None) -> str | None:
    if value and value.startswith("fa:") and not icons.exists(value):
        raise ValueError(f"Unknown Font Awesome icon {value!r}; use fa:<solid|regular|brands>:<name>")
    return value


def check_url(value: str, schemes: tuple[str, ...] = ("http", "https")) -> str:
    """A well-formed absolute URL with one of the given schemes, a host, and no embedded credentials.

    Rejects whitespace, control characters and backslashes (which browsers may "repair" into
    something else), so the stored value is exactly what a browser will follow.
    """
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 or ch == "\\" for ch in value):
        raise ValueError("URLs can't contain spaces, control characters or backslashes")
    try:
        parts = urlsplit(value)
        port = parts.port  # raises for a malformed port
    except ValueError as exc:
        raise ValueError("Not a valid URL") from exc
    if parts.scheme.lower() not in schemes:
        raise ValueError(f"The URL must start with {' or '.join(s + '://' for s in schemes)}")
    if not parts.hostname or "@" in parts.netloc:
        raise ValueError("The URL needs a host name and can't contain a user name or password")
    if port == 0:
        raise ValueError("Not a valid URL")
    return value


def check_link(value: str | None) -> str | None:
    return check_url(value) if value else value


def _image(value: str | None) -> str | None:
    # Images load in every visitor's browser: https only, so they never cause mixed content.
    if value and not value.startswith("media:"):
        check_url(value, ("https",))
    return value


def _icon(value: str | None) -> str | None:
    if value and not value.startswith(("media:", "fa:")):
        check_url(value, ("https",))
    return _known_icon(value)


# Image references: an upload from POST /api/v1/media ("media:<sha256>") or an https URL.
ImageRef = Annotated[
    str | None,
    Field(
        default=None,
        max_length=2048,
        pattern=r"^(media:[0-9a-f]{64}|https://\S+)$",
        description='Uploaded image ("media:<sha256>" from POST /api/v1/media) or an https URL',
    ),
    AfterValidator(_image),
]
# Monitor icons additionally accept a bundled Font Awesome icon.
IconRef = Annotated[
    str | None,
    Field(
        default=None,
        max_length=2048,
        pattern=r"^(fa:(solid|regular|brands):[a-z0-9-]+|media:[0-9a-f]{64}|https://\S+)$",
        description='Font Awesome icon ("fa:brands:github"), an upload ("media:<sha256>") or an https image URL',
    ),
    AfterValidator(_icon),
]
LinkUrl = Annotated[
    str | None,
    Field(default=None, max_length=2048, pattern=r"^https?://\S+$", description="http(s) link"),
    AfterValidator(check_link),
]
