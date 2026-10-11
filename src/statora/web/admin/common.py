from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from statora.db.models import User
from statora.web.deps import local_path
from statora.web.templating import templates


async def rollback(session, user: User, *objects) -> None:
    """Undo a failed write before re-rendering a form.

    Rolling back expires every loaded object, including the signed-in user the layout renders,
    and async sessions can't lazy-load, so reload the user and any objects the template uses.
    """
    await session.rollback()
    for obj in (user, *objects):
        await session.refresh(obj)


def render(request: Request, template: str, user: User, status_code: int = 200, **context: Any):
    return templates.TemplateResponse(
        request,
        template,
        {"user": user, "nav": request.url.path, "flash": request.session.pop("flash", None), **context},
        status_code=status_code,
    )


def flash(request: Request, message: str, kind: str = "success") -> None:
    request.session["flash"] = {"message": message, "kind": kind}


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(local_path(url), status_code=303)


def error_messages(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        messages = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"] if part != "body")
            msg = err["msg"].removeprefix("Value error, ")
            messages.append(f"{loc}: {msg}" if loc else msg)
        return messages
    return [str(exc)]


def checkbox(form, name: str) -> bool:
    return form.get(name) in ("on", "true", "1", "yes")


def opt(value: Any) -> str | None:
    """Empty form strings become None."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def int_list(form, name: str) -> list[int]:
    return [int(v) for v in form.getlist(name) if str(v).strip().isdigit()]
