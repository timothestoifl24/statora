"""Login rate limiting (web login and POST /api/v1/auth/token).

Three counters per attempt, all in a fixed window of `login_rate_window` seconds:

- per client address: stops one client from trying many accounts;
- per client address and account: stops one client from guessing one password;
- per account, with a much higher ceiling: still caps guessing spread over many addresses,
  without letting a single client lock somebody else out of their account. Attempts a client
  makes after it is blocked don't count towards it.
"""

import hashlib
from dataclasses import dataclass

from statora import cache
from statora.config import get_settings

_PREFIX = "statora:ratelimit:login:"
# How many times the per-client limit an account takes before it is closed to every client.
ACCOUNT_LIMIT_FACTOR = 10

# One atomic step (Redis 6+), so a counter is never left without a TTL, which would block its key
# for good. A key without a TTL (from an older version) gets one too.
# KEYS: client, client+account, account. ARGV: window, client limit, account limit.
_HIT = """
local function bump(key, window)
    local count = redis.call('incr', key)
    if redis.call('ttl', key) < 0 then
        redis.call('expire', key, window)
    end
    return count
end
local window = tonumber(ARGV[1])
local client = bump(KEYS[1], window)
local client_account = bump(KEYS[2], window)
if client > tonumber(ARGV[2]) or client_account > tonumber(ARGV[2]) then
    return 0
end
if bump(KEYS[3], window) > tonumber(ARGV[3]) then
    return 0
end
return 1
"""


@dataclass(frozen=True)
class LoginKeys:
    client: str
    client_account: str
    account: str


def login_keys(client_ip: str, username: str) -> LoginKeys:
    # A hash keeps keys short for any username without merging different accounts.
    account = "user:" + hashlib.sha256(username.strip().lower().encode()).hexdigest()
    return LoginKeys(client=f"ip:{client_ip}", client_account=f"ip:{client_ip}:{account}", account=account)


async def hit(keys: LoginKeys) -> bool:
    """Count one login attempt; False once a counter is over its limit."""
    settings = get_settings()
    allowed = await cache.get_redis().eval(
        _HIT,
        3,
        _PREFIX + keys.client,
        _PREFIX + keys.client_account,
        _PREFIX + keys.account,
        settings.login_rate_window,
        settings.login_rate_limit,
        settings.login_rate_limit * ACCOUNT_LIMIT_FACTOR,
    )
    return bool(allowed)


async def succeeded(keys: LoginKeys) -> None:
    """A successful login clears this client's counter for the account. The account-wide counter
    runs out on its own, so a sign-in doesn't reopen guessing spread over many addresses."""
    await cache.get_redis().delete(_PREFIX + keys.client_account)
