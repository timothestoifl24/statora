import time

import httpx

from statora.db.models import MonitorType
from statora.schemas.monitor import HttpConfig, decrypt_sensitive

from .base import CheckResult, CheckTarget
from .guard import refusal

USER_AGENT = "statora-monitor/0.1"
# Only a keyword check reads the body, and only this much of it.
MAX_BODY_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


async def _read_body(response: httpx.Response) -> str:
    body = bytearray()
    # Re-chunked by httpx, so a compressed response that decodes into one huge piece arrives in
    # small parts; only what still fits is kept, so the buffer never grows past the limit.
    async for chunk in response.aiter_bytes(chunk_size=READ_CHUNK_BYTES):
        body += chunk[: MAX_BODY_BYTES - len(body)]
        if len(body) >= MAX_BODY_BYTES:
            break
    return bytes(body).decode(response.encoding or "utf-8", errors="replace")


class BlockedTarget(httpx.RequestError):
    """A request (usually a redirect) refused by the target guard: a blocked network, or a
    lookup that took longer than the check may."""


def _refuse_blocked(timeout_s: float):
    async def hook(request: httpx.Request) -> None:
        # Runs for the first request and for every redirect it follows.
        if problem := await refusal(request.url.host, timeout_s):
            raise BlockedTarget(problem, request=request)

    return hook


async def check_http(target: CheckTarget) -> CheckResult:
    cfg = HttpConfig.model_validate(decrypt_sensitive(MonitorType.HTTP, target.config))
    headers = {"User-Agent": USER_AGENT, **cfg.headers}
    start = time.perf_counter()
    text = None
    try:
        async with (
            httpx.AsyncClient(
                timeout=target.timeout_s,
                follow_redirects=cfg.follow_redirects,
                verify=cfg.verify_tls,
                event_hooks={"request": [_refuse_blocked(target.timeout_s)]},
            ) as client,
            client.stream(cfg.method, target.target, headers=headers, content=cfg.body) as response,
        ):
            # The time until the status line and headers: a large body would otherwise count as
            # latency, and it isn't downloaded at all unless a keyword has to be found in it.
            latency = (time.perf_counter() - start) * 1000
            if cfg.keyword and cfg.status_ok(response.status_code):
                text = await _read_body(response)
    except BlockedTarget as exc:
        return CheckResult.down(str(exc))
    except httpx.TimeoutException:
        return CheckResult.down(f"Timeout after {target.timeout_s}s")
    except httpx.HTTPError as exc:
        return CheckResult.down(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)

    if not cfg.status_ok(response.status_code):
        return CheckResult.down(f"Unexpected status {response.status_code}", latency)

    if cfg.keyword:
        found = cfg.keyword in text
        if found == cfg.invert_keyword:
            verb = "found" if found else "not found"
            return CheckResult.down(f"Keyword {cfg.keyword!r} {verb}", latency)

    return CheckResult.up(latency, f"HTTP {response.status_code}", cfg.degraded_threshold_ms)
