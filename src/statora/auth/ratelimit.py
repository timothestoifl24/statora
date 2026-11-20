"""Login rate limiting (web login and POST /api/v1/auth/token).

Three counters per attempt, all in a fixed window of `login_rate_window` seconds:

- per client address: stops one client from trying many accounts;
- per client address and account: stops one client from guessing one password;
- per account, with a much higher ceiling: still caps guessing spread over many addresses,
  without letting a single client lock somebody else out of their account.
"""

from dataclasses import dataclass

from statora import cache
from statora.config import get_settings

_PREFIX = "statora:ratelimit:login:"
# How many times the per-client limit an account takes before it is closed to every client.
ACCOUNT_LIMIT_FACTOR = 10
# Usernames are user input: keep the Redis keys they end up in short.
_MAX_USERNAME = 128


@dataclass(frozen=True)
class LoginKeys:
    client: str
    client_account: str
    account: str


def login_keys(client_ip: str, username: str) -> LoginKeys:
    account = f"user:{username.strip().lower()[:_MAX_USERNAME]}"
    return LoginKeys(client=f"ip:{client_ip}", client_account=f"ip:{client_ip}:{account}", account=account)


async def hit(keys: LoginKeys) -> bool:
    """Count one login attempt; False once any counter is over its limit."""
    settings = get_settings()
    limits = {
        keys.client: settings.login_rate_limit,
        keys.client_account: settings.login_rate_limit,
        keys.account: settings.login_rate_limit * ACCOUNT_LIMIT_FACTOR,
    }
    # INCR and EXPIRE in one transaction: a counter left without a TTL (a crash or a Redis error
    # between two separate calls) would block its key for good. NX keeps the window fixed.
    async with cache.get_redis().pipeline(transaction=True) as pipe:
        for key in limits:
            pipe.incr(_PREFIX + key)
            pipe.expire(_PREFIX + key, settings.login_rate_window, nx=True)
        results = await pipe.execute()
    counts = results[::2]
    return all(count <= limit for count, limit in zip(counts, limits.values(), strict=True))


async def succeeded(keys: LoginKeys) -> None:
    """A successful login clears this client's counter for the account. The account-wide counter
    runs out on its own, so a sign-in doesn't reopen guessing spread over many addresses."""
    await cache.get_redis().delete(_PREFIX + keys.client_account)
