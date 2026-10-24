"""Turning raw check results into monitor state, heartbeats and daily statistics."""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.checks import CheckResult
from statora.db.base import utcnow
from statora.db.models import (
    Heartbeat,
    Maintenance,
    Monitor,
    MonitorDailyStat,
    MonitorStatus,
    maintenance_monitors,
)

# Which daily counter each recorded status increments.
STATUS_COUNTER = {
    MonitorStatus.UP: "up_count",
    MonitorStatus.PENDING: "up_count",
    MonitorStatus.DEGRADED: "degraded_count",
    MonitorStatus.DOWN: "down_count",
    MonitorStatus.MAINTENANCE: "maintenance_count",
}


async def monitors_in_maintenance(session: AsyncSession, at: datetime | None = None) -> set[int]:
    at = at or utcnow()
    rows = await session.execute(
        select(maintenance_monitors.c.monitor_id)
        .join(Maintenance, Maintenance.id == maintenance_monitors.c.maintenance_id)
        .where(Maintenance.starts_at <= at, Maintenance.ends_at > at)
    )
    return set(rows.scalars())


def resolve_status(monitor: Monitor, result: CheckResult, in_maintenance: bool) -> MonitorStatus:
    """Apply maintenance and the retry budget to a raw check result."""
    if in_maintenance:
        return MonitorStatus.MAINTENANCE
    if result.status != MonitorStatus.DOWN:
        return result.status
    # Already down: stay down. Otherwise tolerate `retries` failures as "pending".
    if monitor.status == MonitorStatus.DOWN or monitor.consecutive_failures >= monitor.retries:
        return MonitorStatus.DOWN
    return MonitorStatus.PENDING


async def record_result(
    session: AsyncSession,
    monitor: Monitor,
    result: CheckResult,
    *,
    in_maintenance: bool = False,
    now: datetime | None = None,
) -> Heartbeat:
    now = now or utcnow()
    status = resolve_status(monitor, result, in_maintenance)
    previous = MonitorStatus(monitor.status)
    # "pending" never counts as a change: it is the absence of a verdict.
    changed = status != previous and status != MonitorStatus.PENDING

    monitor.consecutive_failures = monitor.consecutive_failures + 1 if result.status == "down" else 0
    if changed:
        monitor.status = status
        monitor.status_changed_at = now
    monitor.last_checked_at = now
    monitor.last_latency_ms = result.latency_ms
    monitor.last_message = result.message

    heartbeat = Heartbeat(
        monitor_id=monitor.id,
        ts=now,
        status=status,
        latency_ms=result.latency_ms,
        message=result.message,
        important=changed,
    )
    session.add(heartbeat)
    await _bump_daily_stat(session, monitor.id, now, status, result.latency_ms)

    await cache.set_json(
        cache.monitor_state_key(monitor.id),
        {"status": monitor.status, "latency_ms": result.latency_ms, "checked_at": now.isoformat()},
    )
    if changed:
        await cache.invalidate_pages()
    return heartbeat


async def _bump_daily_stat(
    session: AsyncSession, monitor_id: int, now: datetime, status: MonitorStatus, latency: float | None
) -> None:
    column = STATUS_COUNTER[status]
    values = {
        "monitor_id": monitor_id,
        "day": now.date(),
        column: 1,
        "latency_sum_ms": latency or 0.0,
        "latency_count": 1 if latency is not None else 0,
    }
    table = MonitorDailyStat.__table__
    stmt = insert(table).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["monitor_id", "day"],
        set_={
            column: getattr(table.c, column) + 1,
            "latency_sum_ms": table.c.latency_sum_ms + values["latency_sum_ms"],
            "latency_count": table.c.latency_count + values["latency_count"],
        },
    )
    await session.execute(stmt)


async def purge_old_heartbeats(session: AsyncSession, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    result = await session.execute(delete(Heartbeat).where(Heartbeat.ts < cutoff))
    return result.rowcount or 0


async def uptime_since(session: AsyncSession, monitor_id: int, since: datetime) -> float | None:
    """Uptime ratio from raw heartbeats, ignoring maintenance."""
    counts = dict(
        (
            await session.execute(
                select(Heartbeat.status, func.count())
                .where(Heartbeat.monitor_id == monitor_id, Heartbeat.ts >= since)
                .group_by(Heartbeat.status)
            )
        ).all()
    )
    counts.pop(MonitorStatus.MAINTENANCE, None)
    total = sum(counts.values())
    if not total:
        return None
    return (total - counts.get(MonitorStatus.DOWN, 0)) / total


async def uptime_days(session: AsyncSession, monitor_ids: list[int], days: int) -> dict[int, float | None]:
    """Uptime ratio per monitor over the last `days` days, from the daily rollup."""
    since = (utcnow() - timedelta(days=days - 1)).date()
    rows = await session.execute(
        select(
            MonitorDailyStat.monitor_id,
            func.sum(MonitorDailyStat.up_count + MonitorDailyStat.degraded_count),
            func.sum(
                MonitorDailyStat.up_count + MonitorDailyStat.degraded_count + MonitorDailyStat.down_count
            ),
        )
        .where(MonitorDailyStat.monitor_id.in_(monitor_ids), MonitorDailyStat.day >= since)
        .group_by(MonitorDailyStat.monitor_id)
    )
    result: dict[int, float | None] = dict.fromkeys(monitor_ids)
    for monitor_id, ok, total in rows.all():
        result[monitor_id] = ok / total if total else None
    return result
