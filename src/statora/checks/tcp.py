import asyncio
import time

from statora.schemas.monitor import TcpConfig

from .base import CheckResult, CheckTarget


async def check_tcp(target: CheckTarget) -> CheckResult:
    cfg = TcpConfig.model_validate(target.config)
    start = time.perf_counter()
    try:
        async with asyncio.timeout(target.timeout_s):
            _, writer = await asyncio.open_connection(target.target, cfg.port)
    except TimeoutError:
        return CheckResult.down(f"Timeout connecting to {target.target}:{cfg.port}")
    except OSError as exc:
        return CheckResult.down(f"Connection to {target.target}:{cfg.port} failed: {exc.strerror or exc}")
    latency = (time.perf_counter() - start) * 1000
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return CheckResult.up(latency, f"Port {cfg.port} open", cfg.degraded_threshold_ms)
