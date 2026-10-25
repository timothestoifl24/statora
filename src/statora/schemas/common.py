from typing import Annotated, Generic, TypeVar

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


# Image references: an upload from POST /api/v1/media ("media:<sha256>") or an http(s) URL.
ImageRef = Annotated[
    str | None,
    Field(
        default=None,
        max_length=2048,
        pattern=r"^(media:[0-9a-f]{64}|https?://\S+)$",
        description='Uploaded image ("media:<sha256>" from POST /api/v1/media) or an http(s) URL',
    ),
]
# Monitor icons additionally accept a bundled Font Awesome icon.
IconRef = Annotated[
    str | None,
    Field(
        default=None,
        max_length=2048,
        pattern=r"^(fa:(solid|regular|brands):[a-z0-9-]+|media:[0-9a-f]{64}|https?://\S+)$",
        description='Font Awesome icon ("fa:brands:github"), an upload ("media:<sha256>") or an http(s) image URL',
    ),
    AfterValidator(_known_icon),
]
LinkUrl = Annotated[
    str | None,
    Field(default=None, max_length=2048, pattern=r"^https?://\S+$", description="http(s) link"),
]
