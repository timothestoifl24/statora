"""Redis access: cache helpers, monitor state, leader lock and pub/sub."""

import json
import uuid
from typing import Any

from redis.asyncio import Redis

from statora.config import get_settings

MONITORS_CHANGED_CHANNEL = "statora:monitors:changed"

_redis: Redis | None = None


def init_redis(url: str | None = None, client: Redis | None = None) -> Redis:
    global _redis
    _redis = client or Redis.from_url(url or get_settings().redis_url, decode_responses=True)
    return _redis


def get_redis() -> Redis:
    if _redis is None:
        return init_redis()
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None


def page_key(slug: str) -> str:
    return f"statora:page:{slug}"


def monitor_state_key(monitor_id: int) -> str:
    return f"statora:monitor:{monitor_id}:state"


def token_key(token_hash: str) -> str:
    return f"statora:token:{token_hash}"


async def get_json(key: str) -> Any | None:
    raw = await get_redis().get(key)
    return json.loads(raw) if raw is not None else None


async def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    await get_redis().set(key, json.dumps(value, default=str), ex=ttl)


async def invalidate_pages() -> None:
    """Drop every cached status page; cheap because there are only a handful of pages."""
    redis = get_redis()
    keys = [key async for key in redis.scan_iter(match=page_key("*"))]
    if keys:
        await redis.delete(*keys)


async def publish_monitors_changed(monitor_id: int | None = None) -> None:
    await get_redis().publish(MONITORS_CHANGED_CHANNEL, str(monitor_id or ""))


class LeaderLock:
    """A renewable Redis lock so that only one replica runs the scheduler."""

    _RENEW = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('pexpire', KEYS[1], ARGV[2])
    end
    return 0
    """
    _RELEASE = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """

    def __init__(self, name: str = "statora:scheduler:leader", ttl_ms: int = 15_000) -> None:
        self.name = name
        self.ttl_ms = ttl_ms
        self.token = uuid.uuid4().hex

    async def acquire(self) -> bool:
        return bool(await get_redis().set(self.name, self.token, nx=True, px=self.ttl_ms))

    async def renew(self) -> bool:
        return bool(await get_redis().eval(self._RENEW, 1, self.name, self.token, self.ttl_ms))

    async def release(self) -> None:
        await get_redis().eval(self._RELEASE, 1, self.name, self.token)
