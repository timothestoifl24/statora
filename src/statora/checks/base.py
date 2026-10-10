from dataclasses import dataclass
from typing import Protocol

from statora.db.models import MonitorStatus, MonitorType


@dataclass(frozen=True, slots=True)
class CheckTarget:
    """Plain, session-independent snapshot of a monitor that the checks operate on."""

    id: int
    type: MonitorType
    target: str
    timeout_s: int
    config: dict


@dataclass(frozen=True, slots=True)
class CheckResult:
    status: MonitorStatus
    latency_ms: float | None = None
    message: str | None = None

    @classmethod
    def up(cls, latency_ms: float | None, message: str | None = None, degraded_ms: int | None = None):
        if degraded_ms is not None and latency_ms is not None and latency_ms > degraded_ms:
            return cls(MonitorStatus.DEGRADED, latency_ms, message or f"Slow response ({latency_ms:.0f} ms)")
        return cls(MonitorStatus.UP, latency_ms, message)

    @classmethod
    def down(cls, message: str, latency_ms: float | None = None):
        return cls(MonitorStatus.DOWN, latency_ms, message)


class Check(Protocol):
    async def __call__(self, target: CheckTarget) -> CheckResult: ...
