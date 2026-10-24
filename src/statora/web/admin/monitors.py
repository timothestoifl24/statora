import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.db.base import utcnow
from statora.db.models import Heartbeat, Monitor, MonitorType, User, UserRole, monitor_group_members
from statora.schemas.monitor import CONFIG_MODELS, SECRET_FIELDS, MonitorCreate, MonitorUpdate
from statora.services import crud
from statora.services.monitoring import monitors_in_maintenance, uptime_days, uptime_since
from statora.web.deps import current_user, get_session, local_path, not_found, ui_role

from .common import checkbox, error_messages, flash, int_list, opt, redirect, render, rollback

router = APIRouter()
editor = ui_role(UserRole.EDITOR)


async def _dashboard_rows(session: AsyncSession) -> list[dict]:
    monitors = (await session.scalars(select(Monitor).order_by(Monitor.name))).all()
    ids = [m.id for m in monitors]
    since = utcnow() - timedelta(hours=24)
    uptime: dict[int, float | None] = {}
    if ids:
        uptime_rows = await session.execute(
            select(Heartbeat.monitor_id, func.count().filter(Heartbeat.status != "down"), func.count())
            .where(Heartbeat.monitor_id.in_(ids), Heartbeat.ts >= since, Heartbeat.status != "maintenance")
            .group_by(Heartbeat.monitor_id)
        )
        uptime = {mid: ok / total for mid, ok, total in uptime_rows}

    # Last 30 heartbeats per monitor for the mini status strip.
    recent: dict[int, list[Heartbeat]] = {mid: [] for mid in ids}
    if ids:
        ranked = (
            select(
                Heartbeat.monitor_id,
                Heartbeat.status,
                Heartbeat.ts,
                Heartbeat.latency_ms,
                func.row_number()
                .over(partition_by=Heartbeat.monitor_id, order_by=Heartbeat.ts.desc())
                .label("rn"),
            )
            .where(Heartbeat.monitor_id.in_(ids), Heartbeat.ts >= since)
            .subquery()
        )
        for row in await session.execute(select(ranked).where(ranked.c.rn <= 30).order_by(ranked.c.ts)):
            recent[row.monitor_id].append(row)
    return [{"monitor": m, "uptime_24h": uptime.get(m.id), "recent": recent[m.id]} for m in monitors]


async def dashboard(
    request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    rows = await _dashboard_rows(session)
    counts = {
        s: sum(1 for r in rows if r["monitor"].active and r["monitor"].status == s)
        for s in ("up", "down", "degraded", "pending", "maintenance")
    }
    counts["paused"] = sum(1 for r in rows if not r["monitor"].active)
    template = "admin/_monitor_rows.html" if request.headers.get("HX-Request") else "admin/dashboard.html"
    return render(request, template, user, rows=rows, counts=counts)


async def _member_choices(session: AsyncSession, exclude_id: int | None) -> list[Monitor]:
    query = select(Monitor).order_by(Monitor.name)
    if exclude_id is not None:
        query = query.where(Monitor.id != exclude_id)
    return list((await session.scalars(query)).all())


def _monitor_values(monitor: Monitor | None) -> dict:
    return {
        "name": monitor.name if monitor else "",
        "description": monitor.description if monitor else "",
        "type": monitor.type if monitor else MonitorType.HTTP,
        "target": monitor.target if monitor else "",
        "interval_s": monitor.interval_s if monitor else 60,
        "timeout_s": monitor.timeout_s if monitor else 10,
        "retries": monitor.retries if monitor else 1,
        "active": monitor.active if monitor else True,
        "config": dict(monitor.config) if monitor else {},
        "member_ids": monitor.member_ids if monitor else [],
    }


async def _form_context(
    session: AsyncSession,
    monitor: Monitor | None,
    values: dict | None = None,
    errors: list[str] | None = None,
) -> dict:
    if values is None:
        values = _monitor_values(monitor)
    return {
        "monitor": monitor,
        "values": values,
        "errors": errors or [],
        "types": list(MonitorType),
        "member_choices": await _member_choices(session, monitor.id if monitor else None),
    }


def _config_from_form(form, monitor_type: str) -> dict:
    cfg: dict = {}
    model = CONFIG_MODELS[MonitorType(monitor_type)]
    for name, field in model.model_fields.items():
        key = f"cfg_{name}"
        annotation = str(field.annotation)
        if "bool" in annotation:
            cfg[name] = checkbox(form, key)
            continue
        raw = form.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        raw = str(raw).strip()
        if name == "expected_status":
            cfg[name] = [part.strip() for part in raw.split(",") if part.strip()]
        elif name == "headers":
            cfg[name] = json.loads(raw)
        elif "int" in annotation:
            cfg[name] = int(raw)
        else:
            cfg[name] = raw
    return cfg


def _values_from_form(form) -> dict:
    return {
        "name": str(form.get("name", "")).strip(),
        "description": opt(form.get("description")),
        "type": form.get("type", "http"),
        "target": str(form.get("target", "")).strip(),
        "interval_s": form.get("interval_s") or 60,
        "timeout_s": form.get("timeout_s") or 10,
        "retries": form.get("retries") or 0,
        "active": checkbox(form, "active"),
        "member_ids": int_list(form, "member_ids"),
    }


@router.get("/monitors/new")
async def new_monitor(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    return render(request, "admin/monitor_form.html", user, **await _form_context(session, None))


@router.get("/monitors/{monitor_id}/clone")
async def clone_monitor(
    monitor_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    """The new-monitor form, prefilled from an existing monitor. Nothing is saved until it's submitted."""
    source = await _get(session, monitor_id)
    values = _monitor_values(source) | {"name": f"{source.name} (copy)"[:150], "active": True}
    return render(
        request,
        "admin/monitor_form.html",
        user,
        clone_of=source,
        **await _form_context(session, None, values),
    )


@router.get("/monitors/config-fields")
async def config_fields(
    request: Request,
    type: MonitorType,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    return render(
        request,
        "admin/_monitor_config.html",
        user,
        values={"type": type, "config": {}, "member_ids": []},
        member_choices=await _member_choices(session, None),
    )


@router.post("/monitors/new")
async def create_monitor(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    values = _values_from_form(form)
    clone_id = str(form.get("clone_of") or "")
    clone_of = await session.get(Monitor, int(clone_id)) if clone_id.isdigit() else None
    try:
        values["config"] = _config_from_form(form, values["type"])
        if clone_of is not None and clone_of.type == values["type"]:
            # The form never shows stored secrets, so an empty one is copied (still encrypted)
            # from the original, as editing a monitor keeps it.
            for name in SECRET_FIELDS.get(MonitorType(values["type"]), ()):
                if not values["config"].get(name) and (clone_of.config or {}).get(name):
                    values["config"][name] = clone_of.config[name]
        monitor = await crud.create_monitor(session, MonitorCreate.model_validate(values))
    except (ValidationError, ValueError) as exc:
        values.setdefault("config", {})
        return render(
            request,
            "admin/monitor_form.html",
            user,
            422,
            clone_of=clone_of,
            **await _form_context(session, None, values, error_messages(exc)),
        )
    await session.commit()
    await crud.notify_monitor_changed(monitor.id)
    flash(request, f"Monitor “{monitor.name}” created")
    return redirect(f"/admin/monitors/{monitor.id}")


async def _get(session: AsyncSession, monitor_id: int) -> Monitor:
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise not_found("Monitor")
    return monitor


@router.get("/monitors/{monitor_id}")
async def monitor_detail(
    monitor_id: int,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    monitor = await _get(session, monitor_id)
    since = utcnow() - timedelta(hours=24)
    beats = (
        await session.scalars(
            select(Heartbeat)
            .where(Heartbeat.monitor_id == monitor_id, Heartbeat.ts >= since)
            .order_by(Heartbeat.ts)
        )
    ).all()
    events = (
        await session.scalars(
            select(Heartbeat)
            .where(Heartbeat.monitor_id == monitor_id, Heartbeat.important)
            .order_by(Heartbeat.ts.desc())
            .limit(20)
        )
    ).all()
    chart = [
        {"x": b.ts.isoformat(), "y": round(b.latency_ms, 1) if b.latency_ms is not None else None}
        for b in beats
    ]
    latencies = [b.latency_ms for b in beats if b.latency_ms is not None]
    stats = {
        "uptime_24h": await uptime_since(session, monitor_id, since),
        "uptime_30d": (await uptime_days(session, [monitor_id], 30))[monitor_id],
        "avg_latency": sum(latencies) / len(latencies) if latencies else None,
    }
    parent_groups = (
        await session.scalars(
            select(Monitor)
            .join(monitor_group_members, monitor_group_members.c.group_id == Monitor.id)
            .where(monitor_group_members.c.member_id == monitor_id)
            .order_by(Monitor.name)
        )
    ).all()
    return render(
        request,
        "admin/monitor_detail.html",
        user,
        monitor=monitor,
        chart=chart,
        events=events,
        stats=stats,
        parent_groups=parent_groups,
        in_maintenance=await monitors_in_maintenance(session) if monitor.is_group else set(),
        secret_fields=SECRET_FIELDS.get(MonitorType(monitor.type), ()),
    )


@router.get("/monitors/{monitor_id}/edit")
async def edit_monitor(
    monitor_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    return render(
        request,
        "admin/monitor_form.html",
        user,
        **await _form_context(session, await _get(session, monitor_id)),
    )


@router.post("/monitors/{monitor_id}/edit")
async def update_monitor(
    monitor_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    monitor = await _get(session, monitor_id)
    form = await request.form()
    values = _values_from_form(form)
    values["type"] = monitor.type
    try:
        values["config"] = _config_from_form(form, monitor.type)
        update = MonitorUpdate.model_validate({k: v for k, v in values.items() if k != "type"})
        await crud.update_monitor(session, monitor, update)
    except (ValidationError, ValueError) as exc:
        await rollback(session, user, monitor)
        values.setdefault("config", {})
        return render(
            request,
            "admin/monitor_form.html",
            user,
            422,
            **await _form_context(session, monitor, values, error_messages(exc)),
        )
    await session.commit()
    await crud.notify_monitor_changed(monitor.id)
    flash(request, "Monitor saved")
    return redirect(f"/admin/monitors/{monitor.id}")


@router.post("/monitors/{monitor_id}/toggle")
async def toggle_monitor(
    monitor_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    monitor = await _get(session, monitor_id)
    # The monitor list sends next=/admin to come back to the list; anything off-site is ignored.
    target = local_path(str((await request.form()).get("next") or ""), f"/admin/monitors/{monitor.id}")
    await crud.update_monitor(session, monitor, MonitorUpdate(active=not monitor.active))
    await session.commit()
    await crud.notify_monitor_changed(monitor.id)
    flash(request, f"Monitor “{monitor.name}” {'resumed' if monitor.active else 'paused'}")
    return redirect(target)


@router.post("/monitors/{monitor_id}/delete")
async def delete_monitor(
    monitor_id: int,
    request: Request,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    monitor = await _get(session, monitor_id)
    await session.delete(monitor)
    await session.commit()
    await crud.notify_monitor_changed(monitor_id)
    flash(request, f"Monitor “{monitor.name}” deleted")
    return redirect("/admin")
