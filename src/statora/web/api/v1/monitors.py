from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.base import utcnow
from statora.db.models import Heartbeat, Monitor, MonitorType
from statora.schemas.common import Page
from statora.schemas.monitor import HeartbeatRead, MonitorCreate, MonitorRead, MonitorUpdate, UptimeRead
from statora.services import crud
from statora.services.monitoring import uptime_days, uptime_since
from statora.web.deps import get_session, not_found, write_role

router = APIRouter(prefix="/monitors", tags=["monitors"], dependencies=[Depends(write_role())])


async def _get(session: AsyncSession, monitor_id: int) -> Monitor:
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise not_found("Monitor")
    return monitor


@router.get("", response_model=Page[MonitorRead])
async def list_monitors(
    session: AsyncSession = Depends(get_session),
    name: str | None = Query(default=None, description="Exact name match"),
    type: MonitorType | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = select(Monitor)
    if name is not None:
        query = query.where(Monitor.name == name)
    if type is not None:
        query = query.where(Monitor.type == type)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    items = (await session.scalars(query.order_by(Monitor.id).limit(limit).offset(offset))).all()
    return Page(items=items, total=total or 0, limit=limit, offset=offset)


@router.post("", response_model=MonitorRead, status_code=201)
async def create_monitor(data: MonitorCreate, session: AsyncSession = Depends(get_session)):
    monitor = await crud.create_monitor(session, data)
    await session.commit()
    await crud.notify_monitor_changed(monitor.id)
    return monitor


@router.get("/{monitor_id}", response_model=MonitorRead)
async def get_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)):
    return await _get(session, monitor_id)


@router.patch("/{monitor_id}", response_model=MonitorRead)
async def update_monitor(monitor_id: int, data: MonitorUpdate, session: AsyncSession = Depends(get_session)):
    monitor = await crud.update_monitor(session, await _get(session, monitor_id), data)
    await session.commit()
    await crud.notify_monitor_changed(monitor.id)
    return monitor


@router.put("/{monitor_id}", response_model=MonitorRead)
async def replace_monitor(monitor_id: int, data: MonitorCreate, session: AsyncSession = Depends(get_session)):
    monitor = await _get(session, monitor_id)
    if data.type != monitor.type:
        monitor.type = data.type
    monitor = await crud.update_monitor(
        session, monitor, MonitorUpdate.model_validate(data.model_dump(exclude={"type"}))
    )
    await session.commit()
    await crud.notify_monitor_changed(monitor.id)
    return monitor


@router.delete("/{monitor_id}", status_code=204)
async def delete_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)):
    monitor = await session.get(Monitor, monitor_id)
    if monitor is not None:
        await session.delete(monitor)
        await session.commit()
        await crud.notify_monitor_changed(monitor_id)
    return Response(status_code=204)


@router.get("/{monitor_id}/heartbeats", response_model=list[HeartbeatRead])
async def list_heartbeats(
    monitor_id: int,
    session: AsyncSession = Depends(get_session),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    important_only: bool = False,
    limit: int = Query(default=500, ge=1, le=5000),
):
    await _get(session, monitor_id)
    query = select(Heartbeat).where(
        Heartbeat.monitor_id == monitor_id, Heartbeat.ts >= utcnow() - timedelta(hours=hours)
    )
    if important_only:
        query = query.where(Heartbeat.important)
    return (await session.scalars(query.order_by(Heartbeat.ts.desc()).limit(limit))).all()


@router.get("/{monitor_id}/uptime", response_model=UptimeRead)
async def get_uptime(monitor_id: int, session: AsyncSession = Depends(get_session)):
    await _get(session, monitor_id)
    since = utcnow() - timedelta(hours=24)
    avg = await session.scalar(
        select(func.avg(Heartbeat.latency_ms)).where(
            Heartbeat.monitor_id == monitor_id, Heartbeat.ts >= since
        )
    )
    return UptimeRead(
        monitor_id=monitor_id,
        uptime_24h=await uptime_since(session, monitor_id, since),
        uptime_7d=(await uptime_days(session, [monitor_id], 7))[monitor_id],
        uptime_30d=(await uptime_days(session, [monitor_id], 30))[monitor_id],
        uptime_90d=(await uptime_days(session, [monitor_id], 90))[monitor_id],
        avg_latency_24h_ms=avg,
    )
