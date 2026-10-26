"""Build the Font Awesome icon catalog used by the monitor icon picker and the public pages.

Usage: python scripts/build_fa_catalog.py path/to/fontawesome-free/metadata/icon-families.json

Writes two files to src/statora/static/vendor/fontawesome/:
- icons.json: one entry per free icon and style with its SVG path. The server reads it to inline
  icons on public pages, which don't load the webfont.
- icons-index.json: names, styles and search terms only, for the admin icon picker (the admin
  panel draws the icons with the webfont).
"""

import json
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "src/statora/static/vendor/fontawesome"


def main(source: str) -> None:
    families = json.loads(Path(source).read_text())
    icons = []
    for name, meta in sorted(families.items()):
        free = {
            entry["style"]
            for entry in meta.get("familyStylesByLicense", {}).get("free", [])
            if entry["family"] == "classic"
        }
        for style in ("solid", "regular", "brands"):
            svg = meta.get("svgs", {}).get("classic", {}).get(style)
            if style not in free or not svg or not isinstance(svg["path"], str):
                continue
            terms = [meta.get("label", "")] + [str(t) for t in meta.get("search", {}).get("terms", [])]
            icons.append(
                {
                    "n": name,
                    "s": style,
                    "t": " ".join(t.lower() for t in terms if t),
                    "w": int(svg["width"]),
                    "h": int(svg["height"]),
                    "p": svg["path"],
                }
            )
    compact = {"separators": (",", ":")}
    (OUT_DIR / "icons.json").write_text(json.dumps({"version": "6.7.2", "icons": icons}, **compact))
    index = [[i["n"], i["s"], i["t"]] for i in icons]
    (OUT_DIR / "icons-index.json").write_text(json.dumps(index, **compact))
    print(f"{len(icons)} icons -> {OUT_DIR}")


if __name__ == "__main__":
    main(sys.argv[1])
