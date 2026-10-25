import hashlib
from datetime import UTC, datetime
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


def _fmt_since(value) -> str:
    """Compact duration since a timestamp: "45s", "12m", "2h 14m", "3d 4h"."""
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    seconds = max(int((datetime.now(UTC) - value).total_seconds()), 0)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m" if minutes else f"{seconds}s"


# Font Awesome icon per monitor type, used by the dashboard rows and tiles.
MONITOR_TYPE_ICONS = {
    "http": "fa-solid fa-globe",
    "tcp": "fa-solid fa-network-wired",
    "ping": "fa-solid fa-satellite-dish",
    "dns": "fa-solid fa-server",
    "sql": "fa-solid fa-database",
    "group": "fa-solid fa-layer-group",
}

templates.env.globals.update(
    csrf_input=_csrf_input,
    asset=asset,
    csrf_token=csrf_token,
    app_version=__version__,
    type_icons=MONITOR_TYPE_ICONS,
)
templates.env.filters.update(
    dt=_fmt_dt,
    pct=_fmt_pct,
    ms=_fmt_ms,
    since=_fmt_since,
    markdown=lambda text: Markup(render_markdown(text or "")),
)
