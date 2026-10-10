"""Builds the public status page payload (cached in Redis as JSON)."""

from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from statora import cache
from statora.config import get_settings
from statora.db.base import utcnow
from statora.db.models import (
    Incident,
    IncidentImpact,
    IncidentStatus,
    Maintenance,
    MonitorDailyStat,
    MonitorStatus,
    StatusPage,
    maintenance_pages,
)
from statora.services import crud
from statora.services.markdown import render_markdown
from statora.services.monitoring import monitors_in_maintenance

HISTORY_DAYS = 90
PAST_INCIDENT_DAYS = 14


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


def day_level(stat: MonitorDailyStat | None) -> str:
    """Bucket a day for the uptime bar colour."""
    if stat is None or stat.total == 0:
        return "maintenance" if stat and stat.maintenance_count else "none"
    ratio = stat.uptime or 0
    if stat.down_count == 0:
        return "degraded" if stat.degraded_count > stat.total * 0.1 else "up"
    return "partial" if ratio >= 0.95 else "down"


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
    today = now.date()
    first_day = today - timedelta(days=HISTORY_DAYS - 1)
    monitor_ids = [item.monitor_id for group in page.groups for item in group.items]
    # Members of group monitors are listed (expandable) under their group, so load their history too.
    monitor_ids += [m.id for group in page.groups for item in group.items for m in item.monitor.members]

    stats: dict[tuple[int, date], MonitorDailyStat] = {}
    if monitor_ids:
        rows = await session.scalars(
            select(MonitorDailyStat).where(
                MonitorDailyStat.monitor_id.in_(monitor_ids), MonitorDailyStat.day >= first_day
            )
        )
        stats = {(s.monitor_id, s.day): s for s in rows}
    in_maintenance = await monitors_in_maintenance(session, now)
    days = [first_day + timedelta(days=i) for i in range(HISTORY_DAYS)]

    def effective_status(monitor) -> MonitorStatus:
        if not monitor.active:
            return MonitorStatus.PENDING
        if monitor.id in in_maintenance:
            return MonitorStatus.MAINTENANCE
        return MonitorStatus(monitor.status)

    def uptime_pct(monitor_id: int) -> float | None:
        ok = total = 0
        for day in days:
            if stat := stats.get((monitor_id, day)):
                ok += stat.up_count + stat.degraded_count
                total += stat.total
        return round(ok / total * 100, 3) if total else None

    groups, statuses = [], []
    for group in page.groups:
        components = []
        for item in group.items:
            monitor = item.monitor
            status = effective_status(monitor)
            statuses.append(status)
            bars = []
            for day in days:
                stat = stats.get((monitor.id, day))
                bars.append(
                    {
                        "day": day.isoformat(),
                        "level": day_level(stat),
                        "uptime": round(stat.uptime * 100, 2) if stat and stat.uptime is not None else None,
                        "down": stat.down_count if stat else 0,
                    }
                )
            components.append(
                {
                    "id": item.id,
                    "name": item.label,
                    "status": status,
                    "status_label": COMPONENT_LABELS.get(status, "Unknown"),
                    "uptime": uptime_pct(monitor.id),
                    "bars": bars,
                    "group_mode": monitor.config.get("mode") if monitor.is_group else None,
                    "members": [
                        {
                            "name": member.name,
                            "status": (member_status := effective_status(member)),
                            "status_label": COMPONENT_LABELS.get(member_status, "Unknown"),
                            "uptime": uptime_pct(member.id),
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
            "accent_color": page.accent_color,
            "footer_html": render_markdown(page.footer_text or ""),
            "show_powered_by": page.show_powered_by,
        },
        "overall": {"status": overall, "label": OVERALL_LABELS[overall]},
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
