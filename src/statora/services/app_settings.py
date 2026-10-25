"""Instance-wide settings stored in the database (db/models/settings.py)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.models import AppSetting

# Hide the username/password form on the sign-in page (local accounts). Only takes effect while at
# least one authentication provider is enabled; /login?local=1 still shows the form.
HIDE_LOCAL_LOGIN = "hide_local_login"


async def get(session: AsyncSession, key: str, default: Any = None) -> Any:
    setting = await session.get(AppSetting, key)
    return default if setting is None else setting.value


async def put(session: AsyncSession, key: str, value: Any) -> None:
    setting = await session.get(AppSetting, key)
    if setting is None:
        session.add(AppSetting(key=key, value=value))
    else:
        setting.value = value
    await session.flush()
