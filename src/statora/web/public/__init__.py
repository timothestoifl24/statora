from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from statora.services.status import get_page_summary
from statora.web.deps import get_session, not_found
from statora.web.templating import templates

router = APIRouter(include_in_schema=False)

REFRESH_SECONDS = 60


async def _render(request: Request, session: AsyncSession, slug: str | None):
    summary = await get_page_summary(session, slug)
    if summary is None:
        if slug is None:
            return templates.TemplateResponse(request, "public/empty.html", {})
        raise not_found("Status page")
    partial = request.headers.get("HX-Request") == "true"
    template = "public/_content.html" if partial else "public/page.html"
    response = templates.TemplateResponse(
        request, template, {"s": summary, "refresh": REFRESH_SECONDS, "slug": slug}
    )
    response.headers["Cache-Control"] = "public, max-age=15"
    return response


@router.get("/", response_class=HTMLResponse)
async def default_page(request: Request, session: AsyncSession = Depends(get_session)):
    return await _render(request, session, None)


@router.get("/s/{slug}", response_class=HTMLResponse)
async def status_page(slug: str, request: Request, session: AsyncSession = Depends(get_session)):
    return await _render(request, session, slug)
