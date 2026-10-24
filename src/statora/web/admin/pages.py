import json

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statora import cache
from statora.db.models import HistoryResolution, Monitor, StatusPage, User, UserRole
from statora.schemas.pages import StatusPageCreate, StatusPageUpdate
from statora.services import crud
from statora.web.deps import current_user, get_session, not_found, ui_role

from .common import checkbox, error_messages, flash, opt, redirect, render, rollback

router = APIRouter(prefix="/pages")
editor = ui_role(UserRole.EDITOR)


@router.get("")
async def list_pages(
    request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    pages = (await session.scalars(crud.page_query().order_by(StatusPage.title))).all()
    return render(request, "admin/pages_list.html", user, pages=pages)


async def _monitor_choices(session: AsyncSession) -> list[dict]:
    monitors = (await session.scalars(select(Monitor).order_by(Monitor.name))).all()
    return [{"id": m.id, "name": m.name, "type": m.type} for m in monitors]


def _values(page: StatusPage | None) -> dict:
    if page is None:
        return {
            "slug": "",
            "title": "",
            "description": "",
            "logo_url": "",
            "accent_color": "#1f6feb",
            "footer_text": "",
            "published": True,
            "is_default": False,
            "show_powered_by": True,
            "history_resolution": HistoryResolution.DAY,
            "groups": [],
        }
    return {
        "slug": page.slug,
        "title": page.title,
        "description": page.description or "",
        "logo_url": page.logo_url or "",
        "accent_color": page.accent_color,
        "footer_text": page.footer_text or "",
        "published": page.published,
        "is_default": page.is_default,
        "show_powered_by": page.show_powered_by,
        "history_resolution": page.history_resolution,
        "groups": [
            {
                "name": g.name,
                "items": [{"monitor_id": i.monitor_id, "display_name": i.display_name} for i in g.items],
            }
            for g in page.groups
        ],
    }


def _from_form(form) -> dict:
    try:
        groups = json.loads(form.get("groups_json") or "[]")
    except json.JSONDecodeError:
        groups = []
    return {
        "slug": str(form.get("slug", "")).strip().lower(),
        "title": str(form.get("title", "")).strip(),
        "description": opt(form.get("description")),
        "logo_url": opt(form.get("logo_url")),
        "accent_color": form.get("accent_color") or "#1f6feb",
        "footer_text": opt(form.get("footer_text")),
        "published": checkbox(form, "published"),
        "is_default": checkbox(form, "is_default"),
        "show_powered_by": checkbox(form, "show_powered_by"),
        "history_resolution": form.get("history_resolution") or HistoryResolution.DAY,
        "groups": groups,
    }


async def _form(request, user, session, page, values, errors=None, status=200):
    return render(
        request,
        "admin/page_form.html",
        user,
        status,
        page=page,
        values=values,
        errors=errors or [],
        monitors=await _monitor_choices(session),
    )


@router.get("/new")
async def new_page(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    return await _form(request, user, session, None, _values(None))


@router.post("/new")
async def create_page(
    request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    values = _from_form(await request.form())
    try:
        page = await crud.create_page(session, StatusPageCreate.model_validate(values))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        return await _form(request, user, session, None, values, error_messages(exc), 422)
    await session.commit()
    flash(request, f"Status page “{page.title}” created")
    return redirect("/admin/pages")


async def _get(session: AsyncSession, page_id: int) -> StatusPage:
    page = await session.scalar(crud.page_query().where(StatusPage.id == page_id))
    if page is None:
        raise not_found("Status page")
    return page


@router.get("/{page_id}/edit")
async def edit_page(
    page_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    page = await _get(session, page_id)
    return await _form(request, user, session, page, _values(page))


@router.post("/{page_id}/edit")
async def update_page(
    page_id: int, request: Request, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    page = await _get(session, page_id)
    values = _from_form(await request.form())
    try:
        await crud.update_page(session, page, StatusPageUpdate.model_validate(values))
    except (ValidationError, ValueError) as exc:
        await rollback(session, user)
        page = await _get(session, page_id)
        return await _form(request, user, session, page, values, error_messages(exc), 422)
    await session.commit()
    flash(request, "Status page saved")
    return redirect("/admin/pages")


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
