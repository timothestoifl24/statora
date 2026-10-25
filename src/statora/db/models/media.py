from datetime import datetime

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from statora.db.base import Base, utcnow


class Media(Base):
    """An uploaded image (status page favicon, monitor icon), addressed by its content hash."""

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    content_type: Mapped[str] = mapped_column(String(64))
    size: Mapped[int]
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
