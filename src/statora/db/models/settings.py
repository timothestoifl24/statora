from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from statora.db.base import Base, TimestampMixin

from .auth import JSONType


class AppSetting(TimestampMixin, Base):
    """Instance-wide settings changed in the admin panel (environment variables cover the rest)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType)
