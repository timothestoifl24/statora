"""Font Awesome icon catalog (static/vendor/fontawesome/icons.json, built by scripts/build_fa_catalog.py)."""

import json
import re
from functools import lru_cache
from pathlib import Path

from markupsafe import Markup, escape

from statora.services import media

CATALOG = Path(__file__).resolve().parent.parent / "static/vendor/fontawesome/icons.json"
FA_REF = re.compile(r"^fa:(solid|regular|brands):([a-z0-9-]+)$")


@lru_cache(maxsize=1)
def _catalog() -> dict[tuple[str, str], dict]:
    data = json.loads(CATALOG.read_text())
    return {(icon["s"], icon["n"]): icon for icon in data["icons"]}


def exists(reference: str) -> bool:
    match = FA_REF.match(reference)
    return bool(match) and (match.group(1), match.group(2)) in _catalog()


def icon_html(reference: str | None, cls: str = "") -> Markup:
    """Markup for a monitor icon: inline SVG for Font Awesome icons, <img> for uploads and URLs."""
    if not reference:
        return Markup("")
    if match := FA_REF.match(reference):
        icon = _catalog().get((match.group(1), match.group(2)))
        if icon is None:
            return Markup("")
        return Markup(
            '<svg class="mon-icon {cls}" viewBox="0 0 {w} {h}" fill="currentColor" aria-hidden="true" '
            'focusable="false"><path d="{p}"/></svg>'
        ).format(cls=cls, w=icon["w"], h=icon["h"], p=icon["p"])
    src = media.url(reference)
    if src is None:
        return Markup("")
    return Markup(
        '<img class="mon-icon {cls}" src="{src}" alt="" loading="lazy" referrerpolicy="no-referrer">'
    ).format(cls=cls, src=escape(src))
