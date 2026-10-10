from typing import Generic, TypeVar

from pydantic import BaseModel, Field

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
