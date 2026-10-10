from statora.db.models import MonitorType

from .base import Check, CheckResult, CheckTarget
from .dns import check_dns
from .http import check_http
from .ping import check_ping
from .tcp import check_tcp

CHECKS: dict[MonitorType, Check] = {
    MonitorType.HTTP: check_http,
    MonitorType.TCP: check_tcp,
    MonitorType.PING: check_ping,
    MonitorType.DNS: check_dns,
}


async def run_check(target: CheckTarget) -> CheckResult:
    try:
        return await CHECKS[MonitorType(target.type)](target)
    except Exception as exc:  # a broken check must never kill the scheduler
        return CheckResult.down(f"Check error: {type(exc).__name__}: {exc}")


__all__ = ["CHECKS", "CheckResult", "CheckTarget", "run_check"]
