import ipaddress
from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Example values shipped in this repository (defaults, .env and Kubernetes examples). `statora serve`
# refuses to start with one of them.
PLACEHOLDER_SECRET_KEYS = frozenset({"change-me-in-production", "change-me-to-a-long-random-value"})


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

    # Addresses monitors may not reach, comma-separated: link-local (which includes the
    # 169.254.169.254 cloud metadata service) and the other providers' metadata addresses. Anyone
    # who may edit monitors could otherwise use one to read instance credentials. Empty allows all.
    monitor_blocked_networks: str = "169.254.0.0/16,fe80::/10,fd00:ec2::254/128,100.100.100.200/32"

    @field_validator("monitor_blocked_networks")
    @classmethod
    def _check_networks(cls, value: str) -> str:
        for part in filter(None, (item.strip() for item in value.split(","))):
            ipaddress.ip_network(part, strict=False)  # raises ValueError for a typo
        return value

    @property
    def blocked_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [
            ipaddress.ip_network(part, strict=False)
            for part in filter(None, (item.strip() for item in self.monitor_blocked_networks.split(",")))
        ]

    @property
    def runs_web(self) -> bool:
        return self.role in (Role.ALL, Role.WEB)

    @property
    def runs_worker(self) -> bool:
        return self.role in (Role.ALL, Role.WORKER)


@lru_cache
def get_settings() -> Settings:
    return Settings()
