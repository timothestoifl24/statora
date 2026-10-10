"""Encryption of secrets stored in the database (auth provider passwords, client secrets, keys)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from statora.config import get_settings

_PREFIX = "enc:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(("statora-secrets:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX) :].encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt secret; was STATORA_SECRET_KEY changed?") from exc


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)
