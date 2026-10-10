from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Role(StrEnum):
    ALL = "all"
    WEB = "web"
    WORKER = "worker"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STATORA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://statora:statora@localhost:5432/statora"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = Field(default="change-me-in-production", min_length=16)
    base_url: str = "http://localhost:8000"

    role: Role = Role.ALL
    host: str = "0.0.0.0"
    port: int = 8000

    heartbeat_retention_days: int = 30
    page_cache_ttl: int = 30
    disable_local_login: bool = False
    session_max_age: int = 60 * 60 * 12
    secure_cookies: bool = False

    login_rate_limit: int = 10
    login_rate_window: int = 300

    @property
    def runs_web(self) -> bool:
        return self.role in (Role.ALL, Role.WEB)

    @property
    def runs_worker(self) -> bool:
        return self.role in (Role.ALL, Role.WORKER)


@lru_cache
def get_settings() -> Settings:
    return Settings()
