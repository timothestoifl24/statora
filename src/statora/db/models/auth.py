from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from statora.db.base import Base, TimestampMixin, utcnow

from .enums import AuthProviderType, TokenScope, UserRole

JSONType = JSON().with_variant(JSONB(), "postgresql")


class AuthProvider(TimestampMixin, Base):
    __tablename__ = "auth_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[AuthProviderType] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(default=True)
    # Provider-specific settings; secret values are stored Fernet-encrypted (see auth.crypto).
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    # {"<group name or DN>": "admin|editor|viewer"}
    group_role_mapping: Mapped[dict[str, str]] = mapped_column(JSONType, default=dict)
    auto_create_users: Mapped[bool] = mapped_column(default=True)
    default_role: Mapped[UserRole] = mapped_column(String(16), default=UserRole.VIEWER)
    button_label: Mapped[str | None] = mapped_column(String(100))

    users: Mapped[list["User"]] = relationship(back_populates="auth_provider")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("auth_provider_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(String(16), default=UserRole.VIEWER)
    auth_provider_id: Mapped[int | None] = mapped_column(ForeignKey("auth_providers.id", ondelete="SET NULL"))
    external_id: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None]

    auth_provider: Mapped[AuthProvider | None] = relationship(back_populates="users")
    tokens: Mapped[list["ApiToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def is_local(self) -> bool:
        return self.auth_provider_id is None

    def has_role(self, role: UserRole) -> bool:
        return UserRole(self.role).level >= role.level


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    token_prefix: Mapped[str] = mapped_column(String(16), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[TokenScope]] = mapped_column(JSONType, default=lambda: [TokenScope.READ])
    expires_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship(back_populates="tokens")
