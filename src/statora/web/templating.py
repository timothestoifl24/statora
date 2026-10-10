import hashlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from statora import __version__
from statora.services.markdown import render_markdown
from statora.web.deps import csrf_token

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

templates = Jinja2Templates(directory=TEMPLATE_DIR)


@lru_cache(maxsize=256)
def _file_hash(path: str, mtime_ns: int) -> str:
    return hashlib.sha256((STATIC_DIR / path).read_bytes()).hexdigest()[:10]


def asset(path: str) -> str:
    """URL of a static file with a content hash, so browsers fetch new versions after an update."""
    try:
        version = _file_hash(path, (STATIC_DIR / path).stat().st_mtime_ns)
    except OSError:
        return f"/static/{path}"
    return f"/static/{path}?v={version}"


def _csrf_input(request: Request) -> Markup:
    return Markup('<input type="hidden" name="csrf_token" value="{}">').format(csrf_token(request))


def _fmt_dt(value, fmt: str = "%Y-%m-%d %H:%M UTC") -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime(fmt)


def _fmt_pct(value, digits: int = 2) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def _fmt_ms(value) -> str:
    return "—" if value is None else f"{value:.0f} ms"


templates.env.globals.update(
    csrf_input=_csrf_input,
    asset=asset,
    csrf_token=csrf_token,
    app_version=__version__,
)
templates.env.filters.update(
    dt=_fmt_dt,
    pct=_fmt_pct,
    ms=_fmt_ms,
    markdown=lambda text: Markup(render_markdown(text or "")),
)
