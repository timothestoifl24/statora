from dataclasses import dataclass, field
from typing import Any

from statora.auth import crypto
from statora.db.models import AuthProvider, AuthProviderType
from statora.schemas.auth_provider import CONFIG_MODELS, SECRET_FIELDS


class AuthError(Exception):
    """Login failed; the message is safe to show to the user."""


@dataclass
class ExternalIdentity:
    external_id: str
    username: str
    email: str | None = None
    display_name: str | None = None
    groups: list[str] = field(default_factory=list)


def store_config(
    provider_type: AuthProviderType, config: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate and encrypt a config for storage. Empty secrets keep the previously stored value."""
    provider_type = AuthProviderType(provider_type)
    previous = previous or {}
    data = CONFIG_MODELS[provider_type].model_validate(config).model_dump()
    for name in SECRET_FIELDS[provider_type]:
        value = data.get(name)
        if value:
            data[name] = crypto.encrypt(value)
        elif previous.get(name):
            data[name] = previous[name]
    return data


def load_config(provider: AuthProvider) -> Any:
    """The provider's typed config with secrets decrypted."""
    provider_type = AuthProviderType(provider.type)
    data = dict(provider.config or {})
    for name in SECRET_FIELDS[provider_type]:
        if data.get(name):
            data[name] = crypto.decrypt(data[name])
    return CONFIG_MODELS[provider_type].model_validate(data)


def public_config(provider: AuthProvider) -> dict[str, Any]:
    """Config safe to return through the API / render in the UI: secrets removed."""
    data = dict(provider.config or {})
    for name in SECRET_FIELDS[AuthProviderType(provider.type)]:
        data[name] = None
    return data


def has_secret(provider: AuthProvider, name: str) -> bool:
    return bool((provider.config or {}).get(name))
