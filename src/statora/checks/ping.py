from icmplib import async_ping
from icmplib.exceptions import ICMPLibError

from statora.db.models import MonitorStatus
from statora.schemas.monitor import PingConfig

from .base import CheckResult, CheckTarget


async def check_ping(target: CheckTarget) -> CheckResult:
    cfg = PingConfig.model_validate(target.config)
    try:
        # Unprivileged ICMP sockets: needs net.ipv4.ping_group_range on Linux (set in docker-compose.yml).
        host = await async_ping(
            target.target,
            count=cfg.count,
            interval=0.2,
            timeout=target.timeout_s,
            privileged=False,
        )
    except ICMPLibError as exc:
        return CheckResult.down(f"{type(exc).__name__}: {exc}")
    except PermissionError:
        return CheckResult.down("ICMP not permitted; allow unprivileged ping or add NET_RAW")

    if not host.is_alive:
        return CheckResult.down(f"No reply from {target.target}")
    message = f"{host.packets_received}/{host.packets_sent} replies"
    if host.packet_loss > 0:
        return CheckResult(
            MonitorStatus.DEGRADED, host.avg_rtt, f"Packet loss {host.packet_loss:.0%} ({message})"
        )
    return CheckResult.up(host.avg_rtt, message, cfg.degraded_threshold_ms)
