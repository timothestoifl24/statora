import time

import httpx

from statora.schemas.monitor import HttpConfig

from .base import CheckResult, CheckTarget
from .guard import blocked_address, blocked_message

USER_AGENT = "statora-monitor/0.1"


class BlockedTarget(httpx.RequestError):
    """A request (usually a redirect) to an address in STATORA_MONITOR_BLOCKED_NETWORKS."""


async def _refuse_blocked(request: httpx.Request) -> None:
    # Runs for the first request and for every redirect it follows.
    if address := await blocked_address(request.url.host):
        raise BlockedTarget(blocked_message(request.url.host, address), request=request)


async def check_http(target: CheckTarget) -> CheckResult:
    cfg = HttpConfig.model_validate(target.config)
    headers = {"User-Agent": USER_AGENT, **cfg.headers}
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=target.timeout_s,
            follow_redirects=cfg.follow_redirects,
            verify=cfg.verify_tls,
            event_hooks={"request": [_refuse_blocked]},
        ) as client:
            response = await client.request(cfg.method, target.target, headers=headers, content=cfg.body)
    except BlockedTarget as exc:
        return CheckResult.down(str(exc))
    except httpx.TimeoutException:
        return CheckResult.down(f"Timeout after {target.timeout_s}s")
    except httpx.HTTPError as exc:
        return CheckResult.down(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
    latency = (time.perf_counter() - start) * 1000

    if not cfg.status_ok(response.status_code):
        return CheckResult.down(f"Unexpected status {response.status_code}", latency)

    if cfg.keyword:
        found = cfg.keyword in response.text
        if found == cfg.invert_keyword:
            verb = "found" if found else "not found"
            return CheckResult.down(f"Keyword {cfg.keyword!r} {verb}", latency)

    return CheckResult.up(latency, f"HTTP {response.status_code}", cfg.degraded_threshold_ms)
