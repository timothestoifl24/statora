import logging

from statora.db.models import MonitorType

from .base import Check, CheckResult, CheckTarget
from .dns import check_dns
from .guard import blocked_address, blocked_message, host_of
from .http import check_http
from .ping import check_ping
from .sql import check_sql
from .tcp import check_tcp

log = logging.getLogger(__name__)

# Messages are stored with every heartbeat and shown in the UI: keep unexpected errors short.
MAX_ERROR_MESSAGE = 200

CHECKS: dict[MonitorType, Check] = {
    MonitorType.HTTP: check_http,
    MonitorType.TCP: check_tcp,
    MonitorType.PING: check_ping,
    MonitorType.DNS: check_dns,
    MonitorType.SQL: check_sql,
}


async def run_check(target: CheckTarget) -> CheckResult:
    try:
        host = host_of(target)
        if address := await blocked_address(host):
            return CheckResult.down(blocked_message(host, address))
        return await CHECKS[MonitorType(target.type)](target)
    except Exception as exc:  # a broken check must never kill the scheduler
        # A bug in a check rather than a failing target: log the traceback the heartbeat can't hold.
        log.exception("Check for monitor %s raised", target.id)
        return CheckResult.down(f"Check error: {type(exc).__name__}: {str(exc)[:MAX_ERROR_MESSAGE]}")


__all__ = ["CHECKS", "CheckResult", "CheckTarget", "run_check"]
