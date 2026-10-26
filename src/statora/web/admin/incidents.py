from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.db.base import utcnow
from statora.db.models import (
    Incident,
    IncidentImpact,
    IncidentStatus,
    Maintenance,
    Monitor,
    StatusPage,
    User,
    UserRole,
)
from statora.schemas.pages import (
    IncidentCreate,
    IncidentPatch,
    IncidentUpdateIn,
    MaintenanceCreate,
    MaintenancePatch,
)
from statora.services import crud
from statora.web.deps import current_user, get_session, not_found, ui_role

from .common import done, error_messages, flash, int_list, opt, redirect, render, render_form, rollback

router = APIRouter()
editor = ui_role(UserRole.EDITOR)


async def _choices(session: AsyncSession) -> dict:
    return {
        "all_pages": (await session.scalars(select(StatusPage).order_by(StatusPage.title))).all(),
        "all_monitors": (await session.scalars(select(Monitor).order_by(Monitor.name))).all(),
        "impacts": list(IncidentImpact),
        "statuses": list(IncidentStatus),
    }


# ---------------------------------------------------------------- incidents


@router.get("/incidents")
async def list_incidents(
    request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    incidents = (
        await session.scalars(crud.incident_query().order_by(Incident.started_at.desc()).limit(200))
    ).all()
    pages = {p.id: p for p in (await session.scalars(select(StatusPage))).all()}
    return render(request, "admin/incidents_list.html", user, incidents=incidents, pages=pages)


@router.get("/incidents/open-count")
async def open_incident_count(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    """Badge for the sidebar, loaded with HTMX so every admin page doesn't pay for the query."""
    count = await session.scalar(
        select(func.count()).select_from(Incident).where(Incident.resolved_at.is_(None))
    )
    return HTMLResponse(f'<span class="badge bg-red text-red-fg">{count}</span>' if count else "")


@router.get("/incidents/new")
async def new_incident(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    values = {
        "page_id": None,
        "title": "",
        "impact": "minor",
        "status": "investigating",
        "message": "",
        "monitor_ids": [],
        "ticket_number": "",
        "ticket_url": "",
    }
    return render_form(
        request, "admin/incident_form.html", user, values=values, errors=[], **await _choices(session)
    )


@router.post("/incidents/new")
async def create_incident(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    values = {
        "page_id": form.get("page_id"),
        "title": str(form.get("title", "")).strip(),
        "impact": form.get("impact"),
        "status": form.get("status"),
        "message": str(form.get("message", "")).strip(),
        "monitor_ids": int_list(form, "monitor_ids"),
        **_ticket_from_form(form),
    }
    try:
        incident = await crud.create_incident(session, IncidentCreate.model_validate(values))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        return render_form(
            request,
            "admin/incident_form.html",
            user,
            422,
            values=values,
            errors=error_messages(exc),
            **await _choices(session),
        )
    await session.commit()
    flash(request, "Incident published")
    return done(request, f"/admin/incidents/{incident.id}")


def _ticket_from_form(form) -> dict:
    return {"ticket_number": opt(form.get("ticket_number")), "ticket_url": opt(form.get("ticket_url"))}


async def _get_incident(session: AsyncSession, incident_id: int) -> Incident:
    incident = await session.scalar(crud.incident_query().where(Incident.id == incident_id))
    if incident is None:
        raise not_found("Incident")
    return incident


@router.get("/incidents/{incident_id}")
async def incident_detail(
    incident_id: int,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _render_detail(request, user, session, await _get_incident(session, incident_id))


async def _render_detail(request, user, session, incident, errors=None, status=200, details=None):
    page = await session.get(StatusPage, incident.page_id)
    details = details or {
        "title": incident.title,
        "impact": incident.impact,
        "ticket_number": incident.ticket_number or "",
        "ticket_url": incident.ticket_url or "",
    }
    return render(
        request,
        "admin/incident_detail.html",
        user,
        status,
        incident=incident,
        page=page,
        errors=errors or [],
        details=details,
        statuses=list(IncidentStatus),
        impacts=list(IncidentImpact),
    )


@router.post("/incidents/{incident_id}/edit")
async def edit_incident(
    incident_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    incident = await _get_incident(session, incident_id)
    form = await request.form()
    details = {
        "title": str(form.get("title", "")).strip(),
        "impact": form.get("impact"),
        **_ticket_from_form(form),
    }
    try:
        await crud.patch_incident(session, incident, IncidentPatch.model_validate(details))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        incident = await _get_incident(session, incident_id)
        return await _render_detail(request, user, session, incident, error_messages(exc), 422, details)
    await session.commit()
    flash(request, "Incident details saved")
    return redirect(f"/admin/incidents/{incident_id}")


@router.post("/incidents/{incident_id}/updates")
async def add_update(
    incident_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    incident = await _get_incident(session, incident_id)
    form = await request.form()
    try:
        data = IncidentUpdateIn(status=form.get("status"), body=str(form.get("body", "")).strip())
    except ValidationError as exc:
        return await _render_detail(request, user, session, incident, error_messages(exc), 422)
    await crud.add_incident_update(session, incident, data)
    await session.commit()
    flash(request, "Update posted")
    return redirect(f"/admin/incidents/{incident_id}")


@router.post("/incidents/{incident_id}/delete")
async def delete_incident(
    incident_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    incident = await _get_incident(session, incident_id)
    await session.delete(incident)
    await session.commit()
    await cache.invalidate_pages()
    flash(request, "Incident deleted")
    return redirect("/admin/incidents")


# ---------------------------------------------------------------- maintenance


def _parse_local_dt(value) -> datetime | None:
    """<input type=datetime-local> values are interpreted as UTC."""
    if not value:
        return None
    return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)


def _maintenance_values(m: Maintenance | None) -> dict:
    if m is None:
        start, end = crud.default_maintenance_window()
        return {
            "title": "",
            "body": "",
            "starts_at": start,
            "ends_at": end,
            "monitor_ids": [],
            "page_ids": [],
            "change_number": "",
            "change_url": "",
        }
    return {
        "title": m.title,
        "body": m.body or "",
        "starts_at": m.starts_at,
        "ends_at": m.ends_at,
        "monitor_ids": m.monitor_ids,
        "page_ids": m.page_ids,
        "change_number": m.change_number or "",
        "change_url": m.change_url or "",
    }


def _maintenance_from_form(form) -> dict:
    return {
        "title": str(form.get("title", "")).strip(),
        "body": opt(form.get("body")),
        "starts_at": _parse_local_dt(form.get("starts_at")),
        "ends_at": _parse_local_dt(form.get("ends_at")),
        "monitor_ids": int_list(form, "monitor_ids"),
        "page_ids": int_list(form, "page_ids"),
        "change_number": opt(form.get("change_number")),
        "change_url": opt(form.get("change_url")),
    }


@router.get("/maintenance")
async def list_maintenance(
    request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    items = (
        await session.scalars(crud.maintenance_query().order_by(Maintenance.starts_at.desc()).limit(200))
    ).all()
    return render(request, "admin/maintenance_list.html", user, items=items, now=utcnow())


@router.get("/maintenance/new")
async def new_maintenance(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    return render_form(
        request,
        "admin/maintenance_form.html",
        user,
        item=None,
        values=_maintenance_values(None),
        errors=[],
        **await _choices(session),
    )


@router.post("/maintenance/new")
async def create_maintenance(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    values = _maintenance_from_form(await request.form())
    try:
        await crud.create_maintenance(session, MaintenanceCreate.model_validate(values))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        return render_form(
            request,
            "admin/maintenance_form.html",
            user,
            422,
            item=None,
            values=values,
            errors=error_messages(exc),
            **await _choices(session),
        )
    await session.commit()
    flash(request, "Maintenance scheduled")
    return done(request, "/admin/maintenance")


async def _get_maintenance(session: AsyncSession, item_id: int) -> Maintenance:
    item = await session.scalar(crud.maintenance_query().where(Maintenance.id == item_id))
    if item is None:
        raise not_found("Maintenance")
    return item


@router.get("/maintenance/{item_id}/edit")
async def edit_maintenance(
    item_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    item = await _get_maintenance(session, item_id)
    return render_form(
        request,
        "admin/maintenance_form.html",
        user,
        item=item,
        values=_maintenance_values(item),
        errors=[],
        **await _choices(session),
    )


@router.post("/maintenance/{item_id}/edit")
async def update_maintenance(
    item_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    item = await _get_maintenance(session, item_id)
    values = _maintenance_from_form(await request.form())
    try:
        await crud.patch_maintenance(session, item, MaintenancePatch.model_validate(values))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        item = await _get_maintenance(session, item_id)
        return render_form(
            request,
            "admin/maintenance_form.html",
            user,
            422,
            item=item,
            values=values,
            errors=error_messages(exc),
            **await _choices(session),
        )
    await session.commit()
    flash(request, "Maintenance saved")
    return done(request, "/admin/maintenance")


@router.post("/maintenance/{item_id}/delete")
async def delete_maintenance(
    item_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    item = await _get_maintenance(session, item_id)
    await session.delete(item)
    await session.commit()
    await cache.invalidate_pages()
    flash(request, "Maintenance deleted")
    return redirect("/admin/maintenance")
