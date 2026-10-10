from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.db.models import Incident, IncidentStatus, Maintenance
from statora.schemas.common import Page
from statora.schemas.pages import (
    IncidentCreate,
    IncidentPatch,
    IncidentRead,
    IncidentUpdateIn,
    MaintenanceCreate,
    MaintenancePatch,
    MaintenanceRead,
)
from statora.services import crud
from statora.web.deps import get_session, not_found, write_role

incidents = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(write_role())])
maintenances = APIRouter(prefix="/maintenances", tags=["maintenances"], dependencies=[Depends(write_role())])


async def _get_incident(session: AsyncSession, incident_id: int) -> Incident:
    incident = await session.scalar(crud.incident_query().where(Incident.id == incident_id))
    if incident is None:
        raise not_found("Incident")
    return incident


@incidents.get("", response_model=Page[IncidentRead])
async def list_incidents(
    session: AsyncSession = Depends(get_session),
    page_id: int | None = None,
    status: IncidentStatus | None = None,
    unresolved: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = crud.incident_query()
    if page_id is not None:
        query = query.where(Incident.page_id == page_id)
    if status is not None:
        query = query.where(Incident.status == status)
    if unresolved:
        query = query.where(Incident.status != IncidentStatus.RESOLVED)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    items = (
        await session.scalars(query.order_by(Incident.started_at.desc()).limit(limit).offset(offset))
    ).all()
    return Page(items=items, total=total or 0, limit=limit, offset=offset)


@incidents.post("", response_model=IncidentRead, status_code=201)
async def create_incident(data: IncidentCreate, session: AsyncSession = Depends(get_session)):
    incident = await crud.create_incident(session, data)
    await session.commit()
    session.expunge_all()
    return await _get_incident(session, incident.id)


@incidents.get("/{incident_id}", response_model=IncidentRead)
async def get_incident(incident_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_incident(session, incident_id)


@incidents.patch("/{incident_id}", response_model=IncidentRead)
async def update_incident(
    incident_id: int, data: IncidentPatch, session: AsyncSession = Depends(get_session)
):
    await crud.patch_incident(session, await _get_incident(session, incident_id), data)
    await session.commit()
    session.expunge_all()
    return await _get_incident(session, incident_id)


@incidents.post("/{incident_id}/updates", response_model=IncidentRead, status_code=201)
async def add_incident_update(
    incident_id: int, data: IncidentUpdateIn, session: AsyncSession = Depends(get_session)
):
    await crud.add_incident_update(session, await _get_incident(session, incident_id), data)
    await session.commit()
    session.expunge_all()
    return await _get_incident(session, incident_id)


@incidents.delete("/{incident_id}", status_code=204)
async def delete_incident(incident_id: int, session: AsyncSession = Depends(get_session)):
    incident = await session.get(Incident, incident_id)
    if incident is not None:
        await session.delete(incident)
        await session.commit()
        await cache.invalidate_pages()
    return Response(status_code=204)


async def _get_maintenance(session: AsyncSession, maintenance_id: int) -> Maintenance:
    maintenance = await session.scalar(crud.maintenance_query().where(Maintenance.id == maintenance_id))
    if maintenance is None:
        raise not_found("Maintenance")
    return maintenance


@maintenances.get("", response_model=Page[MaintenanceRead])
async def list_maintenances(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = crud.maintenance_query()
    total = await session.scalar(select(func.count()).select_from(Maintenance))
    items = (
        await session.scalars(query.order_by(Maintenance.starts_at.desc()).limit(limit).offset(offset))
    ).all()
    return Page(items=items, total=total or 0, limit=limit, offset=offset)


@maintenances.post("", response_model=MaintenanceRead, status_code=201)
async def create_maintenance(data: MaintenanceCreate, session: AsyncSession = Depends(get_session)):
    maintenance = await crud.create_maintenance(session, data)
    await session.commit()
    session.expunge_all()
    return await _get_maintenance(session, maintenance.id)


@maintenances.get("/{maintenance_id}", response_model=MaintenanceRead)
async def get_maintenance(maintenance_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_maintenance(session, maintenance_id)


@maintenances.patch("/{maintenance_id}", response_model=MaintenanceRead)
async def update_maintenance(
    maintenance_id: int, data: MaintenancePatch, session: AsyncSession = Depends(get_session)
):
    await crud.patch_maintenance(session, await _get_maintenance(session, maintenance_id), data)
    await session.commit()
    session.expunge_all()
    return await _get_maintenance(session, maintenance_id)


@maintenances.put("/{maintenance_id}", response_model=MaintenanceRead)
async def replace_maintenance(
    maintenance_id: int, data: MaintenanceCreate, session: AsyncSession = Depends(get_session)
):
    await crud.patch_maintenance(
        session, await _get_maintenance(session, maintenance_id), MaintenancePatch(**data.model_dump())
    )
    await session.commit()
    session.expunge_all()
    return await _get_maintenance(session, maintenance_id)


@maintenances.delete("/{maintenance_id}", status_code=204)
async def delete_maintenance(maintenance_id: int, session: AsyncSession = Depends(get_session)):
    maintenance = await session.get(Maintenance, maintenance_id)
    if maintenance is not None:
        await session.delete(maintenance)
        await session.commit()
        await cache.invalidate_pages()
    return Response(status_code=204)
