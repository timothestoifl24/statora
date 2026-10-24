"""Write operations shared by the admin UI and the REST API."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from statora import cache
from statora.auth import crypto
from statora.db.base import utcnow
from statora.db.models import (
    Incident,
    IncidentStatus,
    IncidentUpdate,
    Maintenance,
    Monitor,
    MonitorStatus,
    MonitorType,
    StatusPage,
    StatusPageGroup,
    StatusPageItem,
)
from statora.schemas.monitor import SECRET_FIELDS, MonitorBase, MonitorCreate, MonitorUpdate
from statora.schemas.pages import (
    IncidentCreate,
    IncidentPatch,
    IncidentUpdateIn,
    MaintenanceCreate,
    MaintenancePatch,
    StatusPageCreate,
    StatusPageGroupIn,
    StatusPageUpdate,
)
from statora.services import groups


class ValidationProblem(ValueError):
    """Input that passed schema validation but conflicts with stored data."""


# ---------------------------------------------------------------- monitors


def _store_secrets(monitor_type: str, config: dict, previous: dict | None = None) -> dict:
    """Encrypt secret config fields. An empty value keeps the previously stored secret."""
    config = dict(config)
    for name in SECRET_FIELDS.get(MonitorType(monitor_type), ()):
        value = config.get(name)
        if value and not crypto.is_encrypted(value):
            config[name] = crypto.encrypt(value)
        elif not value and previous and previous.get(name):
            config[name] = previous[name]
    return config


async def create_monitor(session: AsyncSession, data: MonitorCreate) -> Monitor:
    monitor = Monitor(**data.model_dump(exclude={"member_ids"}))
    monitor.config = _store_secrets(monitor.type, monitor.config)
    # Always assign the collection: a lazy load on a freshly inserted object would fail in async code.
    monitor.members = await _group_members(session, None, data.member_ids)
    session.add(monitor)
    await session.flush()
    return monitor


async def update_monitor(session: AsyncSession, monitor: Monitor, data: MonitorUpdate) -> Monitor:
    changes = data.model_dump(exclude_unset=True)
    # Re-validate the full monitor so cross-field rules (timeout < interval, config shape) still hold.
    merged = MonitorBase.model_validate(
        {
            **{f: getattr(monitor, f) for f in MonitorBase.model_fields},
            **changes,
        }
    )
    previous_config = dict(monitor.config or {})
    for field in changes:
        if field != "member_ids":
            setattr(monitor, field, getattr(merged, field))
    if "config" in changes:
        monitor.config = _store_secrets(monitor.type, monitor.config, previous_config)
    if "member_ids" in changes:
        monitor.members = await _group_members(session, monitor.id, merged.member_ids)
    if changes.get("active") is False:
        monitor.status = MonitorStatus.PENDING
    await session.flush()
    return monitor


async def _group_members(session: AsyncSession, group_id: int | None, member_ids: list[int]) -> list[Monitor]:
    if not member_ids:
        return []
    if group_id is not None and group_id in member_ids:
        raise ValidationProblem("A group can't contain itself")
    members = await load_monitors(session, member_ids)
    if await groups.would_create_cycle(session, group_id, member_ids):
        raise ValidationProblem("These members would make the group contain itself (circular groups)")
    order = {mid: i for i, mid in enumerate(member_ids)}
    return sorted(members, key=lambda m: order[m.id])


async def notify_monitor_changed(monitor_id: int | None = None) -> None:
    await cache.publish_monitors_changed(monitor_id)
    await cache.invalidate_pages()


async def load_monitors(session: AsyncSession, ids: list[int]) -> list[Monitor]:
    if not ids:
        return []
    monitors = list((await session.scalars(select(Monitor).where(Monitor.id.in_(ids)))).all())
    missing = set(ids) - {m.id for m in monitors}
    if missing:
        raise ValidationProblem(f"Unknown monitor id(s): {', '.join(map(str, sorted(missing)))}")
    return monitors


# ---------------------------------------------------------------- status pages


def page_query():
    return select(StatusPage).options(
        selectinload(StatusPage.groups)
        .selectinload(StatusPageGroup.items)
        .selectinload(StatusPageItem.monitor)
        # Group members are shown under their group; the relationship's default eager load
        # doesn't reach this deep in a loader chain, so request it explicitly.
        .selectinload(Monitor.members)
    )


async def _slug_taken(session: AsyncSession, slug: str, exclude_id: int | None = None) -> bool:
    query = select(StatusPage.id).where(StatusPage.slug == slug)
    if exclude_id:
        query = query.where(StatusPage.id != exclude_id)
    return bool(await session.scalar(query))


async def _replace_groups(session: AsyncSession, page: StatusPage, groups: list[StatusPageGroupIn]) -> None:
    await load_monitors(session, [item.monitor_id for g in groups for item in g.items])
    page.groups.clear()
    await session.flush()
    for g_pos, group in enumerate(groups):
        page.groups.append(
            StatusPageGroup(
                name=group.name,
                position=g_pos,
                items=[
                    StatusPageItem(monitor_id=item.monitor_id, display_name=item.display_name, position=i_pos)
                    for i_pos, item in enumerate(group.items)
                ],
            )
        )


async def _make_default(session: AsyncSession, page: StatusPage) -> None:
    await session.execute(update(StatusPage).where(StatusPage.id != page.id).values(is_default=False))


async def create_page(session: AsyncSession, data: StatusPageCreate) -> StatusPage:
    if await _slug_taken(session, data.slug):
        raise ValidationProblem(f"Slug {data.slug!r} is already used")
    page = StatusPage(**data.model_dump(exclude={"groups"}), groups=[])
    session.add(page)
    await session.flush()
    await _replace_groups(session, page, data.groups)
    if page.is_default:
        await _make_default(session, page)
    await session.flush()
    await cache.invalidate_pages()
    return page


async def update_page(session: AsyncSession, page: StatusPage, data: StatusPageUpdate) -> StatusPage:
    changes = data.model_dump(exclude_unset=True, exclude={"groups"})
    if "slug" in changes and await _slug_taken(session, changes["slug"], page.id):
        raise ValidationProblem(f"Slug {changes['slug']!r} is already used")
    for field, value in changes.items():
        setattr(page, field, value)
    if data.groups is not None:
        await _replace_groups(session, page, data.groups)
    if page.is_default:
        await _make_default(session, page)
    await session.flush()
    await cache.invalidate_pages()
    return page


# ---------------------------------------------------------------- incidents


def incident_query():
    return select(Incident).options(selectinload(Incident.monitors), selectinload(Incident.updates))


async def create_incident(session: AsyncSession, data: IncidentCreate) -> Incident:
    if not await session.get(StatusPage, data.page_id):
        raise ValidationProblem(f"Unknown status page id {data.page_id}")
    now = utcnow()
    incident = Incident(
        page_id=data.page_id,
        title=data.title,
        impact=data.impact,
        status=data.status,
        started_at=data.started_at or now,
        resolved_at=now if data.status == IncidentStatus.RESOLVED else None,
        ticket_number=data.ticket_number,
        ticket_url=data.ticket_url,
        monitors=await load_monitors(session, data.monitor_ids),
        updates=[IncidentUpdate(status=data.status, body=data.message, created_at=now)],
    )
    session.add(incident)
    await session.flush()
    await cache.invalidate_pages()
    return incident


async def add_incident_update(
    session: AsyncSession, incident: Incident, data: IncidentUpdateIn
) -> IncidentUpdate:
    now = utcnow()
    entry = IncidentUpdate(incident_id=incident.id, status=data.status, body=data.body, created_at=now)
    session.add(entry)
    incident.status = data.status
    incident.resolved_at = now if data.status == IncidentStatus.RESOLVED else None
    await session.flush()
    await session.refresh(incident, ["updates"])
    await cache.invalidate_pages()
    return entry


async def patch_incident(session: AsyncSession, incident: Incident, data: IncidentPatch) -> Incident:
    changes = data.model_dump(exclude_unset=True, exclude={"monitor_ids"})
    for field, value in changes.items():
        setattr(incident, field, value)
    if data.monitor_ids is not None:
        incident.monitors = await load_monitors(session, data.monitor_ids)
    await session.flush()
    await cache.invalidate_pages()
    return incident


# ---------------------------------------------------------------- maintenance


def maintenance_query():
    return select(Maintenance).options(selectinload(Maintenance.monitors), selectinload(Maintenance.pages))


async def _load_pages(session: AsyncSession, ids: list[int]) -> list[StatusPage]:
    if not ids:
        return []
    pages = list((await session.scalars(select(StatusPage).where(StatusPage.id.in_(ids)))).all())
    missing = set(ids) - {p.id for p in pages}
    if missing:
        raise ValidationProblem(f"Unknown status page id(s): {', '.join(map(str, sorted(missing)))}")
    return pages


async def create_maintenance(session: AsyncSession, data: MaintenanceCreate) -> Maintenance:
    maintenance = Maintenance(
        title=data.title,
        body=data.body,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        monitors=await load_monitors(session, data.monitor_ids),
        pages=await _load_pages(session, data.page_ids),
        change_number=data.change_number,
        change_url=data.change_url,
    )
    session.add(maintenance)
    await session.flush()
    await cache.invalidate_pages()
    return maintenance


async def patch_maintenance(
    session: AsyncSession, maintenance: Maintenance, data: MaintenancePatch
) -> Maintenance:
    changes = data.model_dump(exclude_unset=True, exclude={"monitor_ids", "page_ids"})
    for field, value in changes.items():
        setattr(maintenance, field, value)
    if maintenance.ends_at <= maintenance.starts_at:
        raise ValidationProblem("ends_at must be after starts_at")
    if data.monitor_ids is not None:
        maintenance.monitors = await load_monitors(session, data.monitor_ids)
    if data.page_ids is not None:
        maintenance.pages = await _load_pages(session, data.page_ids)
    await session.flush()
    await cache.invalidate_pages()
    return maintenance


def default_maintenance_window() -> tuple:
    start = utcnow().replace(second=0, microsecond=0) + timedelta(hours=1)
    return start, start + timedelta(hours=1)
