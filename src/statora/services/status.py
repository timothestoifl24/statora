"""Builds the public status page payload (cached in Redis as JSON)."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from statora import cache
from statora.config import get_settings
from statora.db.base import utcnow
from statora.db.models import (
    Heartbeat,
    HistoryResolution,
    Incident,
    IncidentImpact,
    IncidentStatus,
    Maintenance,
    MonitorDailyStat,
    MonitorStatus,
    StatusPage,
    maintenance_pages,
)
from statora.services import crud, media
from statora.services.markdown import render_markdown
from statora.services.monitoring import STATUS_COUNTER, monitors_in_maintenance

PAST_INCIDENT_DAYS = 14


@dataclass(frozen=True)
class Window:
    step: timedelta
    bars: int
    span_label: str  # left end of the bar legend
    end_label: str  # right end of the bar legend
    label_format: str  # bar tooltip


HISTORY_WINDOWS = {
    HistoryResolution.MINUTE: Window(timedelta(minutes=1), 120, "2 hours ago", "Now", "%d %b %H:%M UTC"),
    HistoryResolution.HOUR: Window(timedelta(hours=1), 120, "5 days ago", "Now", "%d %b %H:00 UTC"),
    HistoryResolution.DAY: Window(timedelta(days=1), 120, "120 days ago", "Today", "%Y-%m-%d"),
}


@dataclass
class Counts:
    """Heartbeats in one bar, by status (the same counters as MonitorDailyStat)."""

    up_count: int = 0
    degraded_count: int = 0
    down_count: int = 0
    maintenance_count: int = 0
    last_status: str | None = None
    last_ts: datetime | None = None

    @property
    def total(self) -> int:
        return self.up_count + self.degraded_count + self.down_count

    @property
    def uptime(self) -> float | None:
        return (self.up_count + self.degraded_count) / self.total if self.total else None

    def add(self, status: str, count: int, last_ts: datetime) -> None:
        counter = STATUS_COUNTER[MonitorStatus(status)]
        setattr(self, counter, getattr(self, counter) + count)
        if self.last_ts is None or last_ts > self.last_ts:
            self.last_status, self.last_ts = status, last_ts


class Overall(StrEnum):
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"


OVERALL_LABELS = {
    Overall.OPERATIONAL: "All Systems Operational",
    Overall.MAINTENANCE: "Under Maintenance",
    Overall.DEGRADED: "Degraded Performance",
    Overall.PARTIAL_OUTAGE: "Partial System Outage",
    Overall.MAJOR_OUTAGE: "Major System Outage",
}
_SEVERITY = list(Overall)

COMPONENT_LABELS = {
    MonitorStatus.UP: "Operational",
    MonitorStatus.PENDING: "Operational",
    MonitorStatus.DEGRADED: "Degraded Performance",
    MonitorStatus.DOWN: "Outage",
    MonitorStatus.MAINTENANCE: "Under Maintenance",
}
_IMPACT_OVERALL = {
    IncidentImpact.MINOR: Overall.DEGRADED,
    IncidentImpact.MAJOR: Overall.PARTIAL_OUTAGE,
    IncidentImpact.CRITICAL: Overall.MAJOR_OUTAGE,
}


def _worst(*values: Overall) -> Overall:
    return max(values, key=_SEVERITY.index)


def overall_status(
    component_statuses: list[MonitorStatus], incident_impacts: list[IncidentImpact]
) -> Overall:
    result = Overall.OPERATIONAL
    if component_statuses:
        down = sum(s == MonitorStatus.DOWN for s in component_statuses)
        if down and down == len(component_statuses):
            result = Overall.MAJOR_OUTAGE
        elif down:
            result = Overall.PARTIAL_OUTAGE
        elif MonitorStatus.DEGRADED in component_statuses:
            result = Overall.DEGRADED
        elif MonitorStatus.MAINTENANCE in component_statuses:
            result = Overall.MAINTENANCE
    for impact in incident_impacts:
        if impact in _IMPACT_OVERALL:
            result = _worst(result, _IMPACT_OVERALL[impact])
    return result


def bar_level(stat: Counts | MonitorDailyStat | None) -> str:
    """Bucket a bar (a day, hour or minute) for its colour."""
    if stat is None or stat.total == 0:
        return "maintenance" if stat and stat.maintenance_count else "none"
    ratio = stat.uptime or 0
    if stat.down_count == 0:
        return "degraded" if stat.degraded_count > stat.total * 0.1 else "up"
    return "partial" if ratio >= 0.95 else "down"


def bar_starts(resolution: HistoryResolution, now: datetime) -> list[datetime]:
    """Start of every bar in the window, oldest first; the last bar contains `now`."""
    window = HISTORY_WINDOWS[resolution]
    if resolution == HistoryResolution.DAY:
        last = datetime.combine(now.date(), time(), tzinfo=UTC)
    elif resolution == HistoryResolution.HOUR:
        last = now.replace(minute=0, second=0, microsecond=0)
    else:
        last = now.replace(second=0, microsecond=0)
    return [last - window.step * (window.bars - 1 - i) for i in range(window.bars)]


def build_bars(
    resolution: HistoryResolution, starts: list[datetime], buckets: dict[datetime, Counts], interval_s: int
) -> tuple[list[dict[str, Any]], float | None]:
    """Uptime bars and the uptime percentage over the window for one monitor.

    A minute or hour without any check (the monitor checks less often than that) continues the
    previous result, as long as that result is at most one check interval (plus one bar) old.
    Only real checks count towards the uptime percentage.
    """
    window = HISTORY_WINDOWS[resolution]
    earlier = [start for start in buckets if start < starts[0]]
    last = buckets[max(earlier)] if earlier else None
    bars, ok, total = [], 0, 0
    for start in starts:
        counts = buckets.get(start)
        bar = {
            "day": start.date().isoformat(),
            "start": start.isoformat(),
            "label": start.strftime(window.label_format),
            "level": bar_level(counts),
            "uptime": round(counts.uptime * 100, 2) if counts and counts.uptime is not None else None,
            "down": counts.down_count if counts else 0,
        }
        if counts and (counts.total or counts.maintenance_count):
            last = counts
            ok += counts.up_count + counts.degraded_count
            total += counts.total
        elif (
            resolution != HistoryResolution.DAY
            and last is not None
            and last.last_ts is not None
            and start - last.last_ts < timedelta(seconds=interval_s) + window.step
        ):
            # Pending counts as up, like in the daily rollup; other statuses are their own colour.
            bar["level"] = "up" if last.last_status == MonitorStatus.PENDING else last.last_status
            bar["note"] = f"no check · last result {last.last_status} at {last.last_ts:%H:%M} UTC"
        bars.append(bar)
    return bars, round(ok / total * 100, 3) if total else None


async def _history(
    session: AsyncSession, resolution: HistoryResolution, monitors: list, starts: list[datetime]
) -> dict[int, dict[datetime, Counts]]:
    """Counts per monitor and bar start: daily from the rollup, minutes and hours from heartbeats."""
    result: dict[int, dict[datetime, Counts]] = {m.id: {} for m in monitors}
    if not monitors:
        return result
    ids = list(result)
    if resolution == HistoryResolution.DAY:
        rows = await session.scalars(
            select(MonitorDailyStat).where(
                MonitorDailyStat.monitor_id.in_(ids), MonitorDailyStat.day >= starts[0].date()
            )
        )
        for stat in rows:
            result[stat.monitor_id][datetime.combine(stat.day, time(), tzinfo=UTC)] = Counts(
                stat.up_count, stat.degraded_count, stat.down_count, stat.maintenance_count
            )
        return result
    # Look back one check interval before the window, so its first bars can continue that result.
    lookback = timedelta(seconds=min(max(m.interval_s for m in monitors), 86_400))
    # Literal arguments: bound parameters would make GROUP BY see a different expression.
    bucket = func.date_trunc(literal_column(f"'{resolution.value}'"), Heartbeat.ts, literal_column("'UTC'"))
    rows = await session.execute(
        select(Heartbeat.monitor_id, bucket, Heartbeat.status, func.count(), func.max(Heartbeat.ts))
        .where(Heartbeat.monitor_id.in_(ids), Heartbeat.ts >= starts[0] - lookback)
        .group_by(Heartbeat.monitor_id, bucket, Heartbeat.status)
    )
    for monitor_id, start, status, count, last_ts in rows:
        result[monitor_id].setdefault(start.astimezone(UTC), Counts()).add(status, count, last_ts)
    return result


def _incident_dict(incident: Incident) -> dict[str, Any]:
    return {
        "id": incident.id,
        "title": incident.title,
        "impact": incident.impact,
        "status": incident.status,
        "started_at": incident.started_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "updates": [
            {"status": u.status, "body_html": render_markdown(u.body), "created_at": u.created_at.isoformat()}
            for u in incident.updates
        ],
    }


def _maintenance_dict(m: Maintenance, now) -> dict[str, Any]:
    return {
        "id": m.id,
        "title": m.title,
        "body_html": render_markdown(m.body or ""),
        "starts_at": m.starts_at.isoformat(),
        "ends_at": m.ends_at.isoformat(),
        "active": m.is_active(now),
    }


async def build_page_summary(session: AsyncSession, page: StatusPage) -> dict[str, Any]:
    now = utcnow()
    resolution = HistoryResolution(page.history_resolution)
    window = HISTORY_WINDOWS[resolution]
    starts = bar_starts(resolution, now)
    monitors = {item.monitor.id: item.monitor for group in page.groups for item in group.items}
    # Members of group monitors are listed (expandable) under their group, so load their history too.
    monitors |= {m.id: m for group in page.groups for item in group.items for m in item.monitor.members}
    history = await _history(session, resolution, list(monitors.values()), starts)
    in_maintenance = await monitors_in_maintenance(session, now)

    def effective_status(monitor) -> MonitorStatus:
        if not monitor.active:
            return MonitorStatus.PENDING
        if monitor.id in in_maintenance:
            return MonitorStatus.MAINTENANCE
        return MonitorStatus(monitor.status)

    def bars_and_uptime(monitor) -> tuple[list[dict[str, Any]], float | None]:
        return build_bars(resolution, starts, history[monitor.id], monitor.interval_s)

    groups, statuses = [], []
    for group in page.groups:
        components = []
        for item in group.items:
            monitor = item.monitor
            status = effective_status(monitor)
            statuses.append(status)
            bars, uptime = bars_and_uptime(monitor)
            components.append(
                {
                    "id": item.id,
                    "name": item.label,
                    "status": status,
                    "status_label": COMPONENT_LABELS.get(status, "Unknown"),
                    "uptime": uptime,
                    "bars": bars,
                    "group_mode": monitor.config.get("mode") if monitor.is_group else None,
                    "members": [
                        {
                            "name": member.name,
                            "status": (member_status := effective_status(member)),
                            "status_label": COMPONENT_LABELS.get(member_status, "Unknown"),
                            "uptime": bars_and_uptime(member)[1],
                        }
                        for member in monitor.members
                        if member.active
                    ]
                    if monitor.is_group
                    else [],
                }
            )
        groups.append({"name": group.name, "components": components})

    incidents = list(
        (
            await session.scalars(
                crud.incident_query()
                .where(
                    Incident.page_id == page.id,
                    or_(
                        Incident.status != IncidentStatus.RESOLVED,
                        Incident.resolved_at >= now - timedelta(days=PAST_INCIDENT_DAYS),
                    ),
                )
                .order_by(Incident.started_at.desc())
            )
        ).all()
    )
    active = [i for i in incidents if not i.is_resolved]
    past = [i for i in incidents if i.is_resolved]

    maintenances = (
        await session.scalars(
            select(Maintenance)
            .join(maintenance_pages, maintenance_pages.c.maintenance_id == Maintenance.id)
            .where(maintenance_pages.c.page_id == page.id, Maintenance.ends_at > now)
            .options(selectinload(Maintenance.monitors))
            .order_by(Maintenance.starts_at)
        )
    ).all()

    overall = overall_status(statuses, [i.impact for i in active])
    if overall == Overall.OPERATIONAL and any(m.is_active(now) for m in maintenances):
        overall = Overall.MAINTENANCE

    return {
        "page": {
            "slug": page.slug,
            "title": page.title,
            "description_html": render_markdown(page.description or ""),
            "logo_url": page.logo_url,
            "favicon_url": media.url(page.favicon),
            "accent_color": page.accent_color,
            "footer_html": render_markdown(page.footer_text or ""),
            "show_powered_by": page.show_powered_by,
        },
        "overall": {"status": overall, "label": OVERALL_LABELS[overall]},
        "history": {"resolution": resolution, "span_label": window.span_label, "end_label": window.end_label},
        "groups": groups,
        "active_incidents": [_incident_dict(i) for i in active],
        "past_incidents": [_incident_dict(i) for i in past],
        "maintenances": [_maintenance_dict(m, now) for m in maintenances],
        "generated_at": now.isoformat(),
    }


async def get_page_summary(session: AsyncSession, slug: str | None) -> dict[str, Any] | None:
    """Cached summary for a published page; `slug=None` resolves the default page."""
    key = cache.page_key(slug or "__default__")
    cached = await cache.get_json(key)
    if cached is not None:
        return cached

    query = crud.page_query().where(StatusPage.published)
    if slug:
        query = query.where(StatusPage.slug == slug)
    else:
        query = query.order_by(StatusPage.is_default.desc(), StatusPage.id).limit(1)
    page = await session.scalar(query)
    if page is None:
        return None
    summary = await build_page_summary(session, page)
    await cache.set_json(key, summary, get_settings().page_cache_ttl)
    return summary
