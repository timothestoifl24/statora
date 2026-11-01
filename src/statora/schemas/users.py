from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from statora.db.models import TokenScope, UserRole


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, json_schema_extra={"writeOnly": True})
    role: UserRole = UserRole.VIEWER
    active: bool = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(
        default=None, min_length=8, json_schema_extra={"writeOnly": True}, description="Local users only"
    )
    role: UserRole | None = None
    active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    display_name: str | None
    role: UserRole
    active: bool
    auth_provider_id: int | None = Field(description="null for local accounts")
    is_initial_admin: bool = Field(description="Created in the first-run setup; can't be deleted")
    last_login_at: datetime | None
    created_at: datetime


class TokenRequest(BaseModel):
    """Exchange credentials (local or LDAP account) for a new API token."""

    username: str
    password: str = Field(json_schema_extra={"writeOnly": True})
    name: str = Field(default="api", min_length=1, max_length=100)
    scopes: list[TokenScope] = Field(default_factory=lambda: [TokenScope.READ, TokenScope.WRITE])
    expires_in: int | None = Field(
        default=None, ge=60, description="Lifetime in seconds; never expires if null"
    )


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[TokenScope] = Field(default_factory=lambda: [TokenScope.READ])
    expires_in: int | None = Field(
        default=None, ge=60, description="Lifetime in seconds; never expires if null"
    )


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    token_prefix: str
    scopes: list[TokenScope]
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class TokenIssued(TokenRead):
    token: str = Field(description="The full token. Shown only once; store it securely.")
