"""Generate the Statora brand assets: SVG sources, PNG/ICO exports and the web icon set.

    uv run --no-project --with resvg-py --with pillow --with fonttools --with uharfbuzz python assets/make_brand.py

Writes everything to assets/ and copies the files the app serves to src/statora/static/brand/.
"""

import io
import json
import shutil
from pathlib import Path

import resvg_py
import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE
WEB = HERE.parent / "src" / "statora" / "static" / "brand"
# Manrope (SIL Open Font License, see fonts/OFL.txt); the wordmark is converted to outlines.
FONT = HERE / "fonts" / "Manrope-Variable.ttf"

TEAL, BLUE, LIVE = "#12B5A0", "#1F6FEB", "#3DDC97"
NAVY = "#0B1F33"

# userSpaceOnUse so the live dot's halo picks up exactly the tile colour behind it.
GRADIENT = f"""<linearGradient id="g" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{BLUE}"/>
    </linearGradient>"""

PULSE = "M18.5 33H25l3.5-9 5.5 16 3.5-11 2.6 4H45.5"


def mark_group(ring: str, pulse: str, dot_ring: str, stroke: float = 4.5) -> str:
    """Ring + heartbeat + live dot on a 64x64 grid (the tile is drawn separately)."""
    return f"""<circle cx="32" cy="32" r="19" fill="none" stroke="{ring}" stroke-width="{stroke}"/>
    <path d="{PULSE}" fill="none" stroke="{pulse}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="45.4" cy="18.6" r="6.2" fill="{LIVE}" stroke="{dot_ring}" stroke-width="3"/>"""


def tile_icon(stroke: float = 4.5) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Statora">
  <defs>{GRADIENT}</defs>
  <rect width="64" height="64" rx="15" fill="url(#g)"/>
  {mark_group("#fff", "#fff", "url(#g)", stroke)}
</svg>
"""


def plain_mark() -> str:
    # Gradient-stroked mark for transparent backgrounds; the dot keeps a white keyline.
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Statora">
  <defs>{GRADIENT}</defs>
  {mark_group("url(#g)", "url(#g)", "#fff")}
</svg>
"""


def wordmark_path(text: str, size: float, weight: int = 800, tracking: float = -0.012) -> tuple[str, float]:
    font = TTFont(FONT)
    instantiateVariableFont(font, {"wght": weight}, inplace=True)
    buf = io.BytesIO()
    font.save(buf)
    blob = hb.Blob(buf.getvalue())
    hb_font = hb.Font(hb.Face(blob))
    hb_buf = hb.Buffer()
    hb_buf.add_str(text)
    hb_buf.guess_segment_properties()
    hb.shape(hb_font, hb_buf, {"kern": True, "liga": True})

    upem = font["head"].unitsPerEm
    scale = size / upem
    glyph_set = font.getGlyphSet()
    order = font.getGlyphOrder()
    pen = SVGPathPen(glyph_set)
    x = 0.0
    for info, pos in zip(hb_buf.glyph_infos, hb_buf.glyph_positions, strict=True):
        name = order[info.codepoint]
        # Flip Y (font units are y-up) and place on the baseline.
        tpen = TransformPen(pen, (scale, 0, 0, -scale, x + pos.x_offset * scale, 0))
        glyph_set[name].draw(tpen)
        x += pos.x_advance * scale + tracking * size
    return pen.getCommands(), x - tracking * size


def horizontal_logo(text_color: str, dot_ring: str = "#fff", style: str = "") -> str:
    path, width = wordmark_path("Statora", 46)
    gap, mark = 14, 64
    total = mark + gap + width
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total:.1f} 64" role="img" aria-label="Statora">
  <defs>{GRADIENT}</defs>{style}
  <rect width="64" height="64" rx="15" fill="url(#g)"/>
  {mark_group("#fff", "#fff", "url(#g)")}
  <path class="wordmark" transform="translate({mark + gap} 48)" fill="{text_color}" d="{path}"/>
</svg>
"""


def adaptive_logo() -> str:
    # Navy wordmark that turns white when the viewer's colour scheme is dark. Browsers pass the
    # embedding page's color-scheme into SVG images, so this also follows a page's theme toggle.
    style = """
  <style>@media (prefers-color-scheme: dark) { .wordmark { fill: #fff; } }</style>"""
    return horizontal_logo(NAVY, style=style)


def gradient_logo() -> str:
    # Teal-to-blue wordmark, like the docs hero, legible on light and dark backgrounds alike. For
    # places that ignore the viewer's theme, e.g. GitHub, whose own theme switch doesn't reach
    # the README's <picture> or an SVG's prefers-color-scheme. The gradient's coordinates are in
    # the wordmark's own (translated) space, so it spans exactly the text.
    _, width = wordmark_path("Statora", 46)
    style = f"""
  <linearGradient id="w" x1="0" y1="0" x2="{width:.1f}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{BLUE}"/>
    </linearGradient>"""
    return horizontal_logo("url(#w)", style=style)


def og_image(logo_svg_inner: str) -> str:
    path, width = wordmark_path("Statora", 120)
    tag, tag_w = wordmark_path("Uptime monitoring & status pages", 40, weight=600, tracking=0)
    mark = 168
    gap = 36
    block = mark + gap + width
    x0 = (1200 - block) / 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630">
  <defs>{GRADIENT}
    <radialGradient id="bg" cx="0.2" cy="0" r="1.2">
      <stop offset="0" stop-color="#12324f"/><stop offset="1" stop-color="{NAVY}"/>
    </radialGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <g transform="translate({x0:.1f} 186) scale({mark / 64})">
    <rect width="64" height="64" rx="15" fill="url(#g)"/>
    {mark_group("#fff", "#fff", "url(#g)")}
  </g>
  <path transform="translate({x0 + mark + gap:.1f} 312)" fill="#fff" d="{path}"/>
  <path transform="translate({(1200 - tag_w) / 2:.1f} 470)" fill="#9fb3c8" d="{tag}"/>
</svg>
"""


def social_preview() -> str:
    """GitHub social preview (1280x640): light card, centred, everything inside a 40 px margin."""
    title, _ = wordmark_path("Statora", 84)
    _, title_w = wordmark_path("Statora", 84)
    lines = [
        ("Self-hosted uptime monitoring", 394),
        ("with public status pages for your users.", 438),
    ]
    body = ""
    for text, y in lines:
        path, w = wordmark_path(text, 31, weight=500, tracking=0)
        body += f'  <path transform="translate({(1280 - w) / 2:.1f} {y})" fill="#475569" d="{path}"/>\n'

    chip, chip_w = wordmark_path("All systems operational", 24, weight=700, tracking=0)
    dot_r, pad, gap = 8, 26, 14
    pill_w = pad + dot_r * 2 + gap + chip_w + pad
    pill_x = (1280 - pill_w) / 2
    feat, feat_w = wordmark_path("Docker · PostgreSQL · Redis", 24, weight=600, tracking=0)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640" width="1280" height="640" role="img" aria-label="Statora: self-hosted uptime monitoring with public status pages">
  <!-- GitHub social preview. 1280x640 is what GitHub renders best; the card gets cropped to other
       aspect ratios when unfurled, so everything meaningful stays inside a 40 px margin. -->
  <defs>{GRADIENT}
    <linearGradient id="bar" x1="0" y1="0" x2="1280" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{BLUE}"/>
    </linearGradient>
    <linearGradient id="t" x1="0" y1="0" x2="{title_w:.1f}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{BLUE}"/>
    </linearGradient>
  </defs>
  <rect width="1280" height="640" fill="#ffffff"/>
  <!-- Brand bar along the bottom survives cropping better than a full-bleed background. -->
  <rect y="624" width="1280" height="16" fill="url(#bar)"/>
  <rect y="624" width="160" height="16" fill="{LIVE}"/>

  <g transform="translate(576 76) scale(2)">
    <rect width="64" height="64" rx="15" fill="url(#g)"/>
    {mark_group("#fff", "#fff", "url(#g)")}
  </g>

  <path transform="translate({(1280 - title_w) / 2:.1f} 332)" fill="url(#t)" d="{title}"/>
{body}
  <!-- A status chip: the one thing a status page says, and a nod to the live dot in the mark. -->
  <rect x="{pill_x:.1f}" y="476" width="{pill_w:.1f}" height="52" rx="26" fill="#ECFDF5" stroke="#BBF0D6" stroke-width="2"/>
  <circle cx="{pill_x + pad + dot_r:.1f}" cy="502" r="{dot_r + 5}" fill="{LIVE}" opacity=".25"/>
  <circle cx="{pill_x + pad + dot_r:.1f}" cy="502" r="{dot_r}" fill="{LIVE}"/>
  <path transform="translate({pill_x + pad + dot_r * 2 + gap:.1f} 510)" fill="{NAVY}" d="{chip}"/>

  <path transform="translate({(1280 - feat_w) / 2:.1f} 580)" fill="{BLUE}" d="{feat}"/>
</svg>
"""


def render(svg: str, width: int, height: int | None = None) -> Image.Image:
    png = resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height or width)
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "png").mkdir(exist_ok=True)
    icon = tile_icon()
    # Thicker strokes keep the ring and pulse legible at 16-32 px.
    favicon = tile_icon(stroke=6)
    files = {
        "statora-icon.svg": icon,
        "statora-favicon.svg": favicon,
        "statora-mark.svg": plain_mark(),
        "statora-logo.svg": horizontal_logo(NAVY),
        "statora-logo-dark.svg": horizontal_logo("#ffffff"),
        "statora-logo-auto.svg": adaptive_logo(),
        "statora-logo-gradient.svg": gradient_logo(),
        "statora-og.svg": og_image(""),
        "social-preview.svg": social_preview(),
    }
    for name, svg in files.items():
        (OUT / name).write_text(svg)

    for size in (16, 32, 48):
        render(favicon, size).save(OUT / "png" / f"favicon-{size}.png")
    for size in (180, 192, 512, 1024):
        render(icon, size).save(OUT / "png" / f"icon-{size}.png")
    # iOS ignores transparency on touch icons; give it the full-bleed tile (no rounded corners).
    apple = icon.replace('rx="15"', 'rx="0"')
    render(apple, 180).save(OUT / "png" / "apple-touch-icon.png")

    ico_sizes = [16, 32, 48]
    big = render(favicon, 256)
    big.save(OUT / "favicon.ico", sizes=[(s, s) for s in ico_sizes])

    for name in ("statora-logo", "statora-logo-dark"):
        svg = files[f"{name}.svg"]
        vb_w = float(svg.split('viewBox="0 0 ')[1].split(" ")[0])
        h = 128
        render(svg, round(vb_w * h / 64), h).save(OUT / "png" / f"{name}@2x.png")
    render(files["statora-og.svg"], 1200, 630).convert("RGB").save(OUT / "png" / "og-image.png")
    render(files["social-preview.svg"], 1280, 640).convert("RGB").save(OUT / "png" / "social-preview.png")
    write_web_assets(files)
    print("written to", OUT, "and", WEB)


def write_web_assets(files: dict[str, str]) -> None:
    WEB.mkdir(parents=True, exist_ok=True)
    copies = {
        "favicon.svg": OUT / "statora-favicon.svg",
        "favicon.ico": OUT / "favicon.ico",
        "apple-touch-icon.png": OUT / "png" / "apple-touch-icon.png",
        "icon-192.png": OUT / "png" / "icon-192.png",
        "icon-512.png": OUT / "png" / "icon-512.png",
        "icon.svg": OUT / "statora-icon.svg",
        "mark.svg": OUT / "statora-mark.svg",
        "logo.svg": OUT / "statora-logo.svg",
        "logo-dark.svg": OUT / "statora-logo-dark.svg",
        "logo-auto.svg": OUT / "statora-logo-auto.svg",
        "og-image.png": OUT / "png" / "og-image.png",
    }
    for name, src in copies.items():
        shutil.copyfile(src, WEB / name)
    manifest = {
        "name": "Statora",
        "short_name": "Statora",
        "description": "Uptime monitoring and status pages",
        "start_url": "/admin",
        "display": "standalone",
        "background_color": NAVY,
        "theme_color": BLUE,
        "icons": [
            {"src": "/static/brand/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/brand/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/static/brand/icon.svg", "sizes": "any", "type": "image/svg+xml"},
        ],
    }
    (WEB / "site.webmanifest").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
