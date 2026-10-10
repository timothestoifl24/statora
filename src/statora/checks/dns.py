import time

import dns.asyncresolver
import dns.exception
import dns.resolver

from statora.schemas.monitor import DnsConfig

from .base import CheckResult, CheckTarget


def _make_resolver(cfg: DnsConfig) -> dns.asyncresolver.Resolver:
    if cfg.resolver:
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers = [cfg.resolver]
        return resolver
    return dns.asyncresolver.Resolver()


async def check_dns(target: CheckTarget) -> CheckResult:
    cfg = DnsConfig.model_validate(target.config)
    resolver = _make_resolver(cfg)
    start = time.perf_counter()
    try:
        answer = await resolver.resolve(target.target, cfg.record_type, lifetime=target.timeout_s)
    except dns.resolver.NXDOMAIN:
        return CheckResult.down(f"{target.target} does not exist (NXDOMAIN)")
    except dns.resolver.NoAnswer:
        return CheckResult.down(f"No {cfg.record_type} record for {target.target}")
    except dns.exception.Timeout:
        return CheckResult.down(f"DNS timeout after {target.timeout_s}s")
    except dns.exception.DNSException as exc:
        return CheckResult.down(f"DNS error: {exc}")
    latency = (time.perf_counter() - start) * 1000

    values = [rdata.to_text().strip('"') for rdata in answer]
    if cfg.expected_value and not any(cfg.expected_value in value for value in values):
        return CheckResult.down(f"Expected {cfg.expected_value!r}, got {', '.join(values)}", latency)
    return CheckResult.up(latency, ", ".join(values)[:500], cfg.degraded_threshold_ms)
