from statora import cache
from statora.config import get_settings


async def hit(*keys: str) -> bool:
    """Count one login attempt for each key; False once any key is over the limit."""
    settings = get_settings()
    redis = cache.get_redis()
    allowed = True
    for key in keys:
        name = f"statora:ratelimit:login:{key}"
        count = await redis.incr(name)
        if count == 1:
            await redis.expire(name, settings.login_rate_window)
        if count > settings.login_rate_limit:
            allowed = False
    return allowed


async def reset(*keys: str) -> None:
    await cache.get_redis().delete(*(f"statora:ratelimit:login:{key}" for key in keys))
