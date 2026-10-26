import json

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.db.models import HistoryResolution, Monitor, StatusPage, User, UserRole
from statora.schemas.pages import StatusPageCreate, StatusPageUpdate
from statora.services import crud
from statora.services.status import page_overall
from statora.web.deps import current_user, get_session, not_found, ui_role

from .common import checkbox, done, error_messages, flash, opt, redirect, render, render_form, rollback

router = APIRouter(prefix="/pages")
editor = ui_role(UserRole.EDITOR)


@router.get("")
async def list_pages(
    request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    pages = (await session.scalars(crud.page_query().order_by(StatusPage.title))).all()
    # Current overall status of each published page (no uptime history needed for that).
    overall = await page_overall(session, [p for p in pages if p.published])
    return render(request, "admin/pages_list.html", user, pages=pages, overall=overall)


async def _monitor_choices(session: AsyncSession) -> list[dict]:
    monitors = (await session.scalars(select(Monitor).order_by(Monitor.name))).all()
    return [{"id": m.id, "name": m.name, "type": m.type} for m in monitors]


# ---------------------------------------------------------------- settings (modal)

SETTINGS_DEFAULTS = {
    "slug": "",
    "title": "",
    "description": "",
    "logo_url": "",
    "favicon": "",
    "accent_color": "#1f6feb",
    "footer_text": "",
    "published": True,
    "is_default": False,
    "show_powered_by": True,
    "history_resolution": HistoryResolution.DAY,
}


def _settings_values(page: StatusPage | None) -> dict:
    if page is None:
        return dict(SETTINGS_DEFAULTS)
    return {key: getattr(page, key) if getattr(page, key) is not None else "" for key in SETTINGS_DEFAULTS}


def _settings_from_form(form) -> dict:
    return {
        "slug": str(form.get("slug", "")).strip().lower(),
        "title": str(form.get("title", "")).strip(),
        "description": opt(form.get("description")),
        "logo_url": opt(form.get("logo_url")),
        "favicon": opt(form.get("favicon")),
        "accent_color": form.get("accent_color") or "#1f6feb",
        "footer_text": opt(form.get("footer_text")),
        "published": checkbox(form, "published"),
        "is_default": checkbox(form, "is_default"),
        "show_powered_by": checkbox(form, "show_powered_by"),
        "history_resolution": form.get("history_resolution") or HistoryResolution.DAY,
    }


def _settings_form(request, user, page, values, errors=None, next_url="/admin/pages"):
    action = f"/admin/pages/{page.id}/settings" if page else "/admin/pages/new"
    return render_form(
        request,
        "admin/page_settings.html",
        user,
        422 if errors else 200,
        page=page,
        values=values,
        errors=errors or [],
        next_url=next_url,
        form_action=action,
        cancel_url=next_url,
    )


def _next_url(form) -> str:
    target = str(form.get("next") or "")
    return target if target.startswith("/admin/pages") else "/admin/pages"


@router.get("/new")
async def new_page(request: Request, user: User = Depends(editor)):
    return _settings_form(request, user, None, _settings_values(None))


@router.post("/new")
async def create_page(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    values = _settings_from_form(await request.form())
    try:
        page = await crud.create_page(session, StatusPageCreate.model_validate(values))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        return _settings_form(request, user, None, values, error_messages(exc))
    await session.commit()
    flash(request, f"Status page “{page.title}” created. Add its components.")
    return done(request, f"/admin/pages/{page.id}/edit")


async def _get(session: AsyncSession, page_id: int) -> StatusPage:
    page = await session.scalar(crud.page_query().where(StatusPage.id == page_id))
    if page is None:
        raise not_found("Status page")
    return page


@router.get("/{page_id}/settings")
async def page_settings(
    page_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    page = await _get(session, page_id)
    next_url = _next_url(request.query_params)
    return _settings_form(request, user, page, _settings_values(page), next_url=next_url)


@router.post("/{page_id}/settings")
async def update_page_settings(
    page_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    page = await _get(session, page_id)
    form = await request.form()
    values, next_url = _settings_from_form(form), _next_url(form)
    try:
        await crud.update_page(session, page, StatusPageUpdate.model_validate(values))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        page = await _get(session, page_id)
        return _settings_form(request, user, page, values, error_messages(exc), next_url)
    await session.commit()
    flash(request, "Status page settings saved")
    return done(request, next_url)


# ---------------------------------------------------------------- components editor


def _groups(page: StatusPage) -> list[dict]:
    return [
        {
            "name": g.name,
            "items": [{"monitor_id": i.monitor_id, "display_name": i.display_name} for i in g.items],
        }
        for g in page.groups
    ]


def _groups_from_form(form) -> list:
    try:
        groups = json.loads(form.get("groups_json") or "[]")
    except json.JSONDecodeError:
        groups = []
    return groups if isinstance(groups, list) else []


async def _components_form(request, user, session, page, groups, errors=None, status=200):
    return render(
        request,
        "admin/page_form.html",
        user,
        status,
        page=page,
        groups=groups,
        errors=errors or [],
        monitors=await _monitor_choices(session),
    )


@router.get("/{page_id}/edit")
async def edit_page(
    page_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    page = await _get(session, page_id)
    return await _components_form(request, user, session, page, _groups(page))


@router.post("/{page_id}/edit")
async def update_page(
    page_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    page = await _get(session, page_id)
    groups = _groups_from_form(await request.form())
    try:
        await crud.update_page(session, page, StatusPageUpdate.model_validate({"groups": groups}))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        page = await _get(session, page_id)
        return await _components_form(request, user, session, page, groups, error_messages(exc), 422)
    await session.commit()
    flash(request, "Components saved")
    return redirect(f"/admin/pages/{page_id}/edit")


@router.post("/{page_id}/delete")
async def delete_page(
    page_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    page = await _get(session, page_id)
    await session.delete(page)
    await session.commit()
    await cache.invalidate_pages()
    flash(request, f"Status page “{page.title}” deleted")
    return redirect("/admin/pages")
