"""Write the REST API's OpenAPI spec to a file, for the website.

    uv run python scripts/export_openapi.py docs/public/openapi.json

pages.yml runs this for main and develop, so each docs channel publishes the spec of its own
branch at <base>openapi.json, where the REST API page offers it for download and to Bruno.
It's the same document an instance serves at /api/openapi.json.
"""

import json
import sys
from pathlib import Path

from statora.main import create_app

# Importers such as Bruno take the first server as the collection's base URL.
SERVERS = [{"url": "http://localhost:8000", "description": "Your Statora instance"}]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} OUTPUT")
    spec = create_app().openapi()
    spec["servers"] = SERVERS
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(spec['paths'])} paths, version {spec['info']['version']})")


if __name__ == "__main__":
    main()
