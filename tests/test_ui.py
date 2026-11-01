import io
import json
import re
from datetime import timedelta

import pytest
import typer
from sqlalchemy import update

from statora.auth import crypto
from statora.auth.service import authenticate_local
from statora.db import session as db
from statora.db.base import utcnow
from statora.db.models import Monitor, User, UserRole

from .conftest import make_user, needs_services

pytestmark = needs_services


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no CSRF token in page"
    return match.group(1)


async def login(client, username="admin", password="password123"):
    page = await client.get("/login")
    response = await client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": csrf_from(page.text),
            "next": "/admin",
        },
    )
    return response


async def test_admin_requires_login(client):
    response = await client.get("/admin")
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


async def test_login_logout_and_bad_password(client):
    await make_user("admin", UserRole.ADMIN)
    bad = await login(client, password="nope")
    assert bad.status_code == 401 and "Invalid username or password" in bad.text

    ok = await login(client)
    assert ok.status_code == 303 and ok.headers["location"] == "/admin"
    dashboard = await client.get("/admin")
    assert dashboard.status_code == 200 and "Monitors" in dashboard.text

    await client.post("/logout", data={"csrf_token": csrf_from(dashboard.text)})
    assert (await client.get("/admin")).status_code == 303


async def test_csrf_is_enforced(client):
    await make_user("admin", UserRole.ADMIN)
    await login(client)
    response = await client.post("/admin/monitors/new", data={"name": "x"})
    assert response.status_code == 403


async def test_open_redirect_is_blocked(client):
    await make_user("admin", UserRole.ADMIN)
    page = await client.get("/login")
    response = await client.post(
        "/login",
        data={
            "username": "admin",
            "password": "password123",
            "csrf_token": csrf_from(page.text),
            "next": "//evil.example",
        },
    )
    assert response.headers["location"] == "/admin"


async def test_create_monitor_and_page_via_forms(client):
    await make_user("admin", UserRole.ADMIN)
    await login(client)
    form_page = await client.get("/admin/monitors/new")
    token = csrf_from(form_page.text)

    invalid = await client.post(
        "/admin/monitors/new",
        data={
            "csrf_token": token,
            "name": "API",
            "type": "http",
            "target": "not-a-url",
            "interval_s": "60",
            "timeout_s": "10",
            "retries": "1",
            "active": "on",
        },
    )
    assert invalid.status_code == 422 and "http://" in invalid.text

    created = await client.post(
        "/admin/monitors/new",
        data={
            "csrf_token": token,
            "name": "API",
            "type": "http",
            "target": "https://api.example",
            "interval_s": "60",
            "timeout_s": "10",
            "retries": "1",
            "active": "on",
            "cfg_method": "GET",
            "cfg_expected_status": "200-299, 301",
            "cfg_follow_redirects": "on",
            "cfg_verify_tls": "on",
        },
    )
    assert created.status_code == 303
    detail = await client.get(created.headers["location"])
    assert detail.status_code == 200 and ">https://api.example</div>" in detail.text
    # Not checked yet: the page polls quickly so the first result shows up without a reload.
    assert 'hx-trigger="every 3s"' in detail.text

    page = await client.post(
        "/admin/pages/new",
        data={
            "csrf_token": token,
            "title": "Public",
            "slug": "public",
            "accent_color": "#ff0000",
            "published": "on",
            "history_resolution": "hour",
        },
    )
    # Creating a page leads straight to its components editor.
    assert page.status_code == 303 and page.headers["location"] == "/admin/pages/1/edit"
    components = await client.post(
        "/admin/pages/1/edit",
        data={
            "csrf_token": token,
            "groups_json": '[{"name": "APIs", "items": [{"monitor_id": 1, "display_name": "Public API"}]}]',
        },
    )
    assert components.status_code == 303
    public = await client.get("/s/public")
    assert public.status_code == 200 and "Public API" in public.text and "#ff0000" in public.text
    assert "5 days ago" in public.text and public.text.count('class="bar ') == 120
    settings = await client.get("/admin/pages/1/settings")
    assert '<option value="hour" selected>' in settings.text


async def test_viewer_cannot_open_editor_pages(client):
    await make_user("viewer", UserRole.VIEWER)
    await login(client, "viewer")
    assert (await client.get("/admin")).status_code == 200
    assert (await client.get("/admin/monitors/new")).status_code == 403
    assert (await client.get("/admin/users")).status_code == 403


async def test_token_ui_shows_token_once(client):
    await make_user("admin", UserRole.ADMIN)
    await login(client)
    page = await client.get("/admin/profile/tokens")
    await client.post(
        "/admin/profile/tokens", data={"csrf_token": csrf_from(page.text), "name": "tf", "write": "on"}
    )
    first = await client.get("/admin/profile/tokens")
    token = re.search(r'value="(st_[^"]+)"', first.text).group(1)
    second = await client.get("/admin/profile/tokens")
    assert token not in second.text
    assert (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200


async def test_public_page_htmx_partial(client, auth):
    await client.post(
        "/api/v1/status-pages", json={"slug": "p", "title": "P", "is_default": True}, headers=auth
    )
    full = await client.get("/")
    assert "<html" in full.text and "All Systems Operational" in full.text
    partial = await client.get("/s/p", headers={"HX-Request": "true"})
    assert "<html" not in partial.text and "All Systems Operational" in partial.text


async def test_powered_by_toggle_and_theme_switch(client, auth):
    page = (
        await client.post("/api/v1/status-pages", json={"slug": "brand", "title": "B"}, headers=auth)
    ).json()
    shown = await client.get("/s/brand")
    assert "Powered by Statora" in shown.text
    assert 'id="theme-toggle"' in shown.text and "js/theme-init.js" in shown.text

    await client.patch(f"/api/v1/status-pages/{page['id']}", json={"show_powered_by": False}, headers=auth)
    hidden = await client.get("/s/brand")
    assert "Powered by Statora" not in hidden.text


async def test_page_editor_links_to_public_page_and_incident_details_edit(client, auth):
    await make_user("editor", UserRole.EDITOR)
    page = (
        await client.post("/api/v1/status-pages", json={"slug": "ops", "title": "Ops"}, headers=auth)
    ).json()
    incident = (
        await client.post(
            "/api/v1/incidents",
            json={"page_id": page["id"], "title": "Slow", "message": "Looking"},
            headers=auth,
        )
    ).json()
    await login(client, "editor")

    editor = await client.get(f"/admin/pages/{page['id']}/edit")
    assert 'href="/s/ops"' in editor.text and "View status page" in editor.text

    detail = await client.get(f"/admin/incidents/{incident['id']}")
    token = csrf_from(detail.text)
    bad = await client.post(
        f"/admin/incidents/{incident['id']}/edit",
        data={"csrf_token": token, "title": "Slow", "impact": "minor", "ticket_url": "javascript:alert(1)"},
    )
    assert bad.status_code == 422
    saved = await client.post(
        f"/admin/incidents/{incident['id']}/edit",
        data={
            "csrf_token": token,
            "title": "Slow API",
            "impact": "major",
            "ticket_number": "INC42",
            "ticket_url": "https://itsm.example.com/INC42",
        },
    )
    assert saved.status_code == 303
    detail = await client.get(f"/admin/incidents/{incident['id']}")
    assert "Slow API" in detail.text and 'href="https://itsm.example.com/INC42"' in detail.text


async def test_invalid_edit_rerenders_form_after_rollback(client, auth):
    # Regression: rolling back expired the signed-in user and the layout crashed lazy-loading it.
    monitor = (
        await client.post(
            "/api/v1/monitors",
            json={"name": "Web", "type": "http", "target": "https://example.org"},
            headers=auth,
        )
    ).json()
    await make_user("ed", UserRole.EDITOR)
    await login(client, "ed")
    form = await client.get(f"/admin/monitors/{monitor['id']}/edit")
    response = await client.post(
        f"/admin/monitors/{monitor['id']}/edit",
        data={
            "csrf_token": csrf_from(form.text),
            "name": "Web",
            "target": "https://example.org",
            "interval_s": "30",
            "timeout_s": "60",
            "retries": "0",
            "active": "on",
        },
    )
    assert response.status_code == 422 and "timeout_s must be smaller" in response.text


async def test_static_assets_are_fingerprinted(client):
    # Regression: browsers kept a stale admin.css after an update because the URL never changed.
    await make_user("admin", UserRole.ADMIN)
    page = await client.get("/login")
    match = re.search(r'/static/css/admin\.css\?v=([0-9a-f]{10})"', page.text)
    assert match, "admin.css is not fingerprinted"
    versioned = await client.get(f"/static/css/admin.css?v={match.group(1)}")
    assert versioned.status_code == 200 and "immutable" in versioned.headers["cache-control"]
    plain = await client.get("/static/brand/icon-192.png")
    assert plain.headers["cache-control"] == "no-cache"


async def test_redundancy_options_only_for_redundancy_groups(client):
    await make_user("admin", UserRole.ADMIN)
    await login(client)
    stack = (await client.get("/admin/monitors/config-fields", params={"type": "group"})).text
    assert 'id="redundancy-options" hidden' in stack  # new groups default to "stack"
    assert "Members that must be up" in stack  # present for the client-side toggle


async def test_monitor_list_options_pause_resume_and_clone(client, auth):
    monitor = (
        await client.post(
            "/api/v1/monitors",
            json={"name": "Shop", "type": "http", "target": "https://shop.example", "interval_s": 120},
            headers=auth,
        )
    ).json()
    await make_user("viewer", UserRole.VIEWER)
    await login(client, "viewer")
    assert "Options for Shop" not in (await client.get("/admin")).text
    assert (await client.get(f"/admin/monitors/{monitor['id']}/clone")).status_code == 403

    await make_user("editor", UserRole.EDITOR)
    client.cookies.clear()
    await login(client, "editor")
    dashboard = await client.get("/admin")
    assert "Options for Shop" in dashboard.text and f"/admin/monitors/{monitor['id']}/clone" in dashboard.text
    token = csrf_from(dashboard.text)

    paused = await client.post(
        f"/admin/monitors/{monitor['id']}/toggle", data={"csrf_token": token, "next": "/admin"}
    )
    assert paused.status_code == 303 and paused.headers["location"] == "/admin"
    assert "paused</span>" in (await client.get("/admin")).text
    resumed = await client.post(
        f"/admin/monitors/{monitor['id']}/toggle", data={"csrf_token": token, "next": "https://evil.example"}
    )
    assert resumed.headers["location"] == f"/admin/monitors/{monitor['id']}"

    clone = await client.get(f"/admin/monitors/{monitor['id']}/clone")
    assert clone.status_code == 200 and 'action="/admin/monitors/new"' in clone.text
    assert 'value="Shop (copy)"' in clone.text and 'value="https://shop.example"' in clone.text
    assert 'value="120"' in clone.text
    created = await client.post(
        "/admin/monitors/new",
        data={
            "csrf_token": token,
            "name": "Shop (copy)",
            "type": "http",
            "target": "https://shop.example",
            "interval_s": "120",
            "timeout_s": "10",
            "retries": "1",
            "active": "on",
            "cfg_method": "GET",
        },
    )
    assert created.status_code == 303
    dashboard = await client.get("/admin")
    assert "Options for Shop (copy)" in dashboard.text and 'Options for Shop"' in dashboard.text


async def test_sql_monitor_form_never_shows_the_password(client):
    await make_user("admin", UserRole.ADMIN)
    await login(client)
    fields = (await client.get("/admin/monitors/config-fields", params={"type": "sql"})).text
    assert 'name="cfg_engine"' in fields and 'name="cfg_password"' in fields and "Stored" not in fields

    token = csrf_from((await client.get("/admin/monitors/new")).text)
    created = await client.post(
        "/admin/monitors/new",
        data={
            "csrf_token": token,
            "name": "Orders DB",
            "type": "sql",
            "target": "db.internal",
            "interval_s": "60",
            "timeout_s": "10",
            "retries": "0",
            "active": "on",
            "cfg_engine": "mysql",
            "cfg_database": "orders",
            "cfg_username": "probe",
            "cfg_password": "hunter22",
            "cfg_verify_tls": "on",
        },
    )
    assert created.status_code == 303, created.text
    detail = (await client.get(created.headers["location"])).text
    assert "mysql://db.internal:3306/orders" in detail
    assert "hunter22" not in detail and "enc:" not in detail and ">Password<" not in detail

    edit = (await client.get(created.headers["location"] + "/edit")).text
    assert "Stored — leave empty to keep" in edit and "hunter22" not in edit and "enc:" not in edit


async def test_clone_keeps_the_stored_sql_password(client, auth, session):
    config = {"engine": "postgresql", "database": "orders", "username": "probe", "password": "hunter22"}
    source = (
        await client.post(
            "/api/v1/monitors",
            json={"name": "Orders DB", "type": "sql", "target": "db.internal", "config": config},
            headers=auth,
        )
    ).json()
    await make_user("editor", UserRole.EDITOR)
    await login(client, "editor")

    form = (await client.get(f"/admin/monitors/{source['id']}/clone")).text
    assert f'name="clone_of" value="{source["id"]}"' in form
    assert "Stored — leave empty to keep" in form and "hunter22" not in form and "enc:" not in form

    created = await client.post(
        "/admin/monitors/new",
        data={
            "csrf_token": csrf_from(form),
            "clone_of": str(source["id"]),
            "name": "Orders DB (copy)",
            "type": "sql",
            "target": "db2.internal",
            "interval_s": "60",
            "timeout_s": "10",
            "retries": "0",
            "active": "on",
            "cfg_engine": "postgresql",
            "cfg_database": "orders",
            "cfg_username": "probe",
            "cfg_password": "",
        },
    )
    assert created.status_code == 303, created.text
    copy = await session.get(Monitor, int(created.headers["location"].rsplit("/", 1)[1]))
    assert crypto.decrypt(copy.config["password"]) == "hunter22"


async def test_sidebar_shows_open_incident_count(client, auth):
    page = (
        await client.post("/api/v1/status-pages", json={"slug": "inc", "title": "Inc"}, headers=auth)
    ).json()
    await login(client)
    dashboard = await client.get("/admin")
    assert 'class="navbar navbar-vertical' in dashboard.text
    assert 'hx-get="/admin/incidents/open-count"' in dashboard.text
    assert (await client.get("/admin/incidents/open-count")).text == ""

    incident = (
        await client.post(
            "/api/v1/incidents",
            json={"page_id": page["id"], "title": "Down", "message": "Looking"},
            headers=auth,
        )
    ).json()
    assert ">1</span>" in (await client.get("/admin/incidents/open-count")).text

    await client.post(
        f"/api/v1/incidents/{incident['id']}/updates",
        json={"status": "resolved", "body": "Fixed"},
        headers=auth,
    )
    assert (await client.get("/admin/incidents/open-count")).text == ""


async def test_dashboard_lists_problems_first(client, auth, session):
    ids = {}
    for name in ("Alpha", "Bravo", "Charlie", "Delta"):
        created = await client.post(
            "/api/v1/monitors",
            json={"name": name, "type": "http", "target": f"https://{name}.example"},
            headers=auth,
        )
        ids[name] = created.json()["id"]
    statuses = {
        "Alpha": ("up", True),
        "Bravo": ("down", True),
        "Charlie": ("degraded", True),
        "Delta": ("down", False),
    }
    for name, (status, active) in statuses.items():
        monitor = await session.get(Monitor, ids[name])
        monitor.status, monitor.active, monitor.status_changed_at = (
            status,
            active,
            utcnow() - timedelta(minutes=90),
        )
    await session.commit()

    await login(client)
    partial = (await client.get("/admin", headers={"HX-Request": "true"})).text
    order = re.findall(r'data-name="(\w+) https', partial)
    assert order == ["bravo", "charlie", "alpha", "delta"]  # down, degraded, up, then paused
    assert "1 of 3 up" in partial and "2 need attention" in partial
    assert "Down for 1h 30m" in partial and 'data-status="paused"' in partial
    assert 'id="monitor-search"' not in partial  # the toolbar stays outside the refreshed block
    assert 'id="monitor-search"' in (await client.get("/admin")).text


async def test_dashboard_tile_view_and_wallboard(client, auth):
    await client.post(
        "/api/v1/monitors",
        json={"name": "Shop", "type": "http", "target": "https://shop.example"},
        headers=auth,
    )
    await login(client)

    tiles = await client.get("/admin?view=tiles")
    assert 'class="monitor-tiles"' in tiles.text and 'aria-label="Tile view"' in tiles.text
    # The choice is remembered, so the HTMX refresh (plain /admin) keeps returning tiles.
    refreshed = await client.get("/admin", headers={"HX-Request": "true"})
    assert "<html" not in refreshed.text and 'class="monitor-tiles"' in refreshed.text

    kiosk = await client.get("/admin?kiosk=1")
    assert '<body class="kiosk"' in kiosk.text and 'id="monitor-search"' not in kiosk.text
    assert 'hx-get="/admin?kiosk=1"' in kiosk.text and "Exit wallboard" in kiosk.text

    listed = await client.get("/admin?view=list", headers={"HX-Request": "true"})
    assert "monitor-table" in listed.text and "monitor-tiles" not in listed.text


async def test_public_status_card_counts_and_incident_timeline(client, auth):
    page = (
        await client.post(
            "/api/v1/status-pages", json={"slug": "acme", "title": "Acme", "is_default": True}, headers=auth
        )
    ).json()
    ok = (
        await client.post(
            "/api/v1/monitors",
            json={"name": "Web", "type": "http", "target": "https://a.example"},
            headers=auth,
        )
    ).json()
    await client.patch(
        f"/api/v1/status-pages/{page['id']}",
        json={"groups": [{"name": "Platform", "items": [{"monitor_id": ok["id"]}]}]},
        headers=auth,
    )
    calm = (await client.get("/s/acme")).text
    assert 'class="status-card status-operational"' in calm and "All 1 component operational" in calm
    assert "banner" not in calm and '<svg class="icon' in calm

    await client.post(
        "/api/v1/incidents",
        json={"page_id": page["id"], "title": "Mail delays", "impact": "major", "message": "Looking into it"},
        headers=auth,
    )
    busy = (await client.get("/s/acme", headers={"HX-Request": "true"})).text
    assert 'class="status-card status-partial_outage"' in busy
    assert 'class="incident impact-major"' in busy and '<ol class="timeline">' in busy
    assert "Updated <time" in busy  # the timestamp refreshes with the content


def image_bytes(fmt: str = "PNG", size=(32, 32), **save) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGBA" if fmt in ("PNG", "WEBP", "ICO") else "RGB", size, (31, 111, 235, 255)).save(
        out, fmt, **save
    )
    return out.getvalue()


PNG = image_bytes()


async def test_media_upload_validation_and_headers(client, auth):
    ok = await client.post("/api/v1/media", files={"file": ("x.png", PNG, "image/png")}, headers=auth)
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["ref"].startswith("media:") and body["content_type"] == "image/png"
    again = await client.post("/api/v1/media", files={"file": ("y.png", PNG, "image/png")}, headers=auth)
    assert again.json()["ref"] == body["ref"]  # identical files are stored once

    served = await client.get(body["url"])
    assert served.status_code == 200 and served.content.startswith(b"\x89PNG")
    assert served.headers["content-type"] == "image/png"
    assert "sandbox" in served.headers["content-security-policy"]
    assert served.headers["x-content-type-options"] == "nosniff"
    assert (await client.get("/media/" + "0" * 64)).status_code == 404


async def upload(client, auth, name: str, data: bytes, mime: str = "application/octet-stream"):
    return await client.post("/api/v1/media", files={"file": (name, data, mime)}, headers=auth)


async def stored(client, response) -> bytes:
    assert response.status_code == 201, response.text
    return (await client.get(response.json()["url"])).content


async def test_raster_uploads_are_re_encoded(client, auth):
    from PIL import Image, PngImagePlugin

    # Every accepted raster format comes back as a clean, small PNG.
    for fmt, extra in (("JPEG", {}), ("GIF", {}), ("WEBP", {}), ("ICO", {"sizes": [(16, 16), (48, 48)]})):
        data = await stored(
            client, await upload(client, auth, f"i.{fmt.lower()}", image_bytes(fmt, (48, 48), **extra))
        )
        img = Image.open(io.BytesIO(data))
        assert img.format == "PNG" and max(img.size) <= 256, fmt

    # Anything hidden in or after the image is dropped: text chunks, EXIF, appended HTML or ZIP.
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "<script>alert(1)</script>")
    tagged = image_bytes("PNG", info=info)
    exif = Image.Exif()
    exif[0x010E] = "<?php system($_GET['c']); ?>"  # ImageDescription
    payloads = {
        "text.png": tagged,
        "exif.jpg": image_bytes("JPEG", exif=exif),
        "polyglot.png": PNG + b"<html><script>alert(document.cookie)</script></html>",
        "zip.png": PNG + b"PK\x03\x04" + b"evil.exe" + b"\x00" * 64,
    }
    for name, data in payloads.items():
        clean = await stored(client, await upload(client, auth, name, data))
        for marker in (b"<script", b"<?php", b"PK\x03\x04", b"evil.exe", b"alert("):
            assert marker not in clean, (name, marker)

    # Big images shrink to 256 px; oversized dimensions are refused before decoding (decompression bombs).
    big = Image.open(
        io.BytesIO(await stored(client, await upload(client, auth, "b.png", image_bytes("PNG", (1024, 512)))))
    )
    assert big.size == (256, 128)
    bomb = await upload(client, auth, "bomb.png", image_bytes("PNG", (4096, 1)))
    assert bomb.status_code == 422 and "2048" in bomb.json()["detail"]


async def test_rejected_uploads(client, auth):
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    truncated = PNG[: len(PNG) // 2]
    cases = {
        "fake.png": (fake_png, "damaged"),
        "truncated.png": (truncated, "damaged"),
        "page.png": (b"<html><body>hi</body></html>", "Upload a PNG"),
        "tool.exe": (b"MZ\x90\x00" + b"\x00" * 200, "Upload a PNG"),
        "archive.zip": (b"PK\x03\x04" + b"\x00" * 200, "Upload a PNG"),
        "script.png": (b"#!/bin/sh\nrm -rf /\n", "Upload a PNG"),
        "doc.pdf": (b"%PDF-1.7\n" + b"\x00" * 100, "Upload a PNG"),
        "empty.png": (b"", "empty"),
        "big.png": (PNG + b"\x00" * (256 * 1024), "256 KB"),
        "xxe.svg": (
            b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
            "DOCTYPE",
        ),
        "broken.svg": (b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"', "valid XML"),
        "nothing.svg": (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            "Nothing drawable",
        ),
    }
    for name, (data, message) in cases.items():
        response = await upload(client, auth, name, data, "image/png")
        assert response.status_code == 422, (name, response.text)
        detail = response.json()["detail"]
        assert message in detail and "Traceback" not in detail and "PIL" not in detail, (name, detail)

    # The body limit applies before the upload is read.
    huge = await upload(client, auth, "huge.png", b"\x00" * (600 * 1024))
    assert huge.status_code == 413


async def test_svg_uploads_are_rebuilt_from_an_allowlist(client, auth):
    evil = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 24 24" onload="alert(1)">
  <title>icon</title>
  <script>alert(document.cookie)</script>
  <style>@import url(https://evil.example/x.css); svg { background: url(javascript:alert(1)) }</style>
  <defs><linearGradient id="g"><stop offset="0" stop-color="#1f6feb"/></linearGradient></defs>
  <path d="M2 2h20v20H2z" fill="url(#g)" style="stroke:#000;stroke-width:2;fill:url(javascript:alert(1))" onclick="alert(2)"/>
  <circle cx="12" cy="12" r="4" fill="url(https://evil.example/track)"/>
  <a xlink:href="javascript:alert(3)"><rect width="4" height="4"/></a>
  <use xlink:href="https://evil.example/sprite.svg#x"/>
  <use href="#g"/>
  <image href="data:image/svg+xml;base64,PHN2Zz48c2NyaXB0PmFsZXJ0KDEpPC9zY3JpcHQ+PC9zdmc+"/>
  <foreignObject><body xmlns="http://www.w3.org/1999/xhtml"><iframe src="javascript:alert(4)"/></body></foreignObject>
  <animate attributeName="href" values="javascript:alert(5)"/>
  <set attributeName="onmouseover" to="alert(6)"/>
  <rect width="2" height="2" fill="&#106;avascript:alert(7)"/>
</svg>"""
    clean = (await stored(client, await upload(client, auth, "evil.svg", evil, "image/svg+xml"))).decode()
    lowered = clean.lower()
    for bad in (
        "script",
        "onload",
        "onclick",
        "javascript",
        "evil.example",
        "@import",
        "foreignobject",
        "<image",
        "<a ",
        "animate",
        "<set",
        "iframe",
        "data:",
    ):
        assert bad not in lowered, (bad, clean)
    # The drawing itself survives, including internal references and safe style declarations.
    assert 'fill="url(#g)"' in clean and 'stroke="#000"' in clean and 'stroke-width="2"' in clean
    assert '<use href="#g"' in clean and "<title>icon</title>" in clean and 'viewBox="0 0 24 24"' in clean


async def test_status_page_favicon(client, auth):
    ref = (await client.post("/api/v1/media", files={"file": ("f.png", PNG)}, headers=auth)).json()["ref"]
    bad = await client.post(
        "/api/v1/status-pages",
        json={"slug": "fav", "title": "Fav", "favicon": "javascript:alert(1)"},
        headers=auth,
    )
    assert bad.status_code == 422
    page = await client.post(
        "/api/v1/status-pages", json={"slug": "fav", "title": "Fav", "favicon": ref}, headers=auth
    )
    assert page.json()["favicon"] == ref
    public = (await client.get("/s/fav")).text
    assert f'<link rel="icon" href="/media/{ref[6:]}">' in public and "brand/favicon.svg" not in public

    await client.patch(f"/api/v1/status-pages/{page.json()['id']}", json={"favicon": None}, headers=auth)
    assert "brand/favicon.svg" in (await client.get("/s/fav")).text


async def test_status_page_settings_modal_flow(client, auth):
    monitor = (
        await client.post(
            "/api/v1/monitors",
            json={"name": "Web", "type": "http", "target": "https://w.example"},
            headers=auth,
        )
    ).json()
    await client.post("/api/v1/status-pages", json={"slug": "taken", "title": "Taken"}, headers=auth)
    await login(client)
    hx = {"HX-Request": "true", "HX-Target": "app-modal-form"}  # what htmx sends from the modal

    fragment = await client.get("/admin/pages/new", headers=hx)
    assert "<html" not in fragment.text and 'hx-post="/admin/pages/new"' in fragment.text
    token = csrf_from(fragment.text)
    assert "<html" in (await client.get("/admin/pages/new")).text  # works without JavaScript too

    form = {
        "csrf_token": token,
        "title": "Shop",
        "slug": "taken",
        "accent_color": "#123456",
        "published": "on",
    }
    clash = await client.post("/admin/pages/new", data=form, headers=hx)
    assert clash.status_code == 200 and "HX-Redirect" not in clash.headers and "already used" in clash.text

    created = await client.post("/admin/pages/new", data={**form, "slug": "shop"}, headers=hx)
    editor_url = created.headers["HX-Redirect"]
    assert re.fullmatch(r"/admin/pages/\d+/edit", editor_url)
    page_id = editor_url.split("/")[3]

    groups = json.dumps([{"name": "Main", "items": [{"monitor_id": monitor["id"]}]}])
    await client.post(editor_url, data={"csrf_token": token, "groups_json": groups})
    # Saving settings leaves the components alone ...
    saved = await client.post(
        f"/admin/pages/{page_id}/settings",
        data={**form, "slug": "shop", "title": "Shop status", "next": editor_url},
        headers=hx,
    )
    assert saved.headers["HX-Redirect"] == editor_url
    page = (await client.get(f"/api/v1/status-pages/{page_id}", headers=auth)).json()
    assert page["title"] == "Shop status" and page["groups"][0]["items"][0]["monitor_id"] == monitor["id"]
    # ... and saving components leaves the settings alone.
    await client.post(editor_url, data={"csrf_token": token, "groups_json": "[]"})
    page = (await client.get(f"/api/v1/status-pages/{page_id}", headers=auth)).json()
    assert page["title"] == "Shop status" and page["accent_color"] == "#123456" and page["groups"] == []

    listing = (await client.get("/admin/pages")).text
    assert (
        'href="/admin/pages/new" class="btn btn-primary" data-modal' in listing
        and 'id="app-modal"' in listing
    )
    # The "next" target can't leave the status pages section.
    escaped = await client.post(
        f"/admin/pages/{page_id}/settings", data={**form, "slug": "shop", "next": "https://evil.example"}
    )
    assert escaped.headers["location"] == "/admin/pages"


async def test_monitor_icon_and_link(client, auth):
    base = {"name": "Grafana", "type": "http", "target": "https://grafana.example"}
    for bad in (
        {"icon": "fa:brands:not-an-icon"},
        {"icon": "javascript:alert(1)"},
        {"link_url": "javascript:alert(1)"},
    ):
        assert (
            await client.post("/api/v1/monitors", json={**base, **bad}, headers=auth)
        ).status_code == 422, bad
    monitor = (
        await client.post(
            "/api/v1/monitors",
            json={**base, "icon": "fa:brands:github", "link_url": "https://grafana.example/d/home"},
            headers=auth,
        )
    ).json()
    assert monitor["icon"] == "fa:brands:github" and monitor["link_url"] == "https://grafana.example/d/home"

    page = (
        await client.post("/api/v1/status-pages", json={"slug": "apps", "title": "Apps"}, headers=auth)
    ).json()
    await client.patch(
        f"/api/v1/status-pages/{page['id']}",
        json={"groups": [{"name": "Apps", "items": [{"monitor_id": monitor["id"]}]}]},
        headers=auth,
    )
    public = (await client.get("/s/apps")).text
    assert (
        '<a href="https://grafana.example/d/home" class="component-label app-link" target="_blank" rel="noopener noreferrer">'
        in public
    )
    assert '<svg class="mon-icon component-icon" viewBox="0 0 496 512"' in public  # inline SVG, no icon font

    ref = (await client.post("/api/v1/media", files={"file": ("g.png", PNG)}, headers=auth)).json()["ref"]
    await client.patch(
        f"/api/v1/monitors/{monitor['id']}", json={"icon": ref, "link_url": None}, headers=auth
    )
    public = (await client.get("/s/apps")).text
    assert (
        f'<img class="mon-icon component-icon" src="/media/{ref[6:]}"' in public and "app-link" not in public
    )

    await login(client)
    dashboard = (await client.get("/admin")).text
    assert f'src="/media/{ref[6:]}"' in dashboard
    form = (await client.get(f"/admin/monitors/{monitor['id']}/edit")).text
    assert f'name="icon" value="{ref}"' in form and "data-allow-fa" in form


async def test_create_and_edit_forms_open_in_the_modal(client, auth):
    page = (await client.post("/api/v1/status-pages", json={"slug": "m", "title": "M"}, headers=auth)).json()
    monitor = (
        await client.post(
            "/api/v1/monitors",
            json={"name": "Shop", "type": "http", "target": "https://s.example"},
            headers=auth,
        )
    ).json()
    await login(client)
    token = csrf_from((await client.get("/admin")).text)
    load = {"HX-Request": "true", "HX-Target": "app-modal-content"}
    submit = {"HX-Request": "true", "HX-Target": "app-modal-form"}

    forms = [
        "/admin/monitors/new",
        f"/admin/monitors/{monitor['id']}/edit",
        f"/admin/monitors/{monitor['id']}/clone",
        "/admin/incidents/new",
        "/admin/maintenance/new",
        "/admin/users/new",
        f"/admin/pages/{page['id']}/settings",
    ]
    for url in forms:
        fragment = await client.get(url, headers=load)
        assert fragment.status_code == 200 and "<html" not in fragment.text, url
        assert 'id="app-modal-form"' in fragment.text and 'class="modal-header"' in fragment.text, url
        full = await client.get(url)  # direct links and browsers without JavaScript get a page
        assert "<html" in full.text and 'id="admin-form"' in full.text, url
        # Other HTMX requests (like the dashboard refresh) never get the modal fragment.
        assert (
            "<html" in (await client.get(url, headers={"HX-Request": "true", "HX-Target": "content"})).text
        ), url

    invalid = await client.post(
        "/admin/maintenance/new",
        data={"csrf_token": token, "title": "DB", "starts_at": "", "ends_at": ""},
        headers=submit,
    )
    assert (
        invalid.status_code == 200 and "alert-danger" in invalid.text and "HX-Redirect" not in invalid.headers
    )

    created = await client.post(
        "/admin/incidents/new",
        data={
            "csrf_token": token,
            "page_id": page["id"],
            "title": "Down",
            "impact": "minor",
            "status": "investigating",
            "message": "Hm",
        },
        headers=submit,
    )
    assert re.fullmatch(r"/admin/incidents/\d+", created.headers["HX-Redirect"])

    user = await client.post(
        "/admin/users/new",
        data={
            "csrf_token": token,
            "username": "dana",
            "password": "password123",
            "role": "viewer",
            "active": "on",
        },
        headers=submit,
    )
    assert user.headers["HX-Redirect"] == "/admin/users"
    users = (await client.get("/admin/users")).text
    assert 'href="/admin/users/new" class="btn btn-primary" data-modal' in users
    dana = next(
        u
        for u in (await client.get("/api/v1/users", headers=auth)).json()["items"]
        if u["username"] == "dana"
    )
    assert f'href="/admin/users/{dana["id"]}/edit" class="btn btn-sm" data-modal' in users
    edit = (await client.get(f"/admin/users/{dana['id']}/edit", headers=load)).text
    # You can't delete yourself, so check the delete button on another user.
    assert 'form="modal-delete-form"' in edit and 'id="modal-delete-form"' in edit


async def test_auth_provider_forms_open_in_the_modal(client):
    await make_user("admin", UserRole.ADMIN)
    await login(client)
    load = {"HX-Request": "true", "HX-Target": "app-modal-content"}
    submit = {"HX-Request": "true", "HX-Target": "app-modal-form"}
    listing = (await client.get("/admin/settings/auth")).text
    assert 'href="/admin/settings/auth/new/oidc" data-modal' in listing

    new = await client.get("/admin/settings/auth/new/oidc", headers=load)
    assert (
        "<html" not in new.text and 'data-modal-size="xl"' in new.text and "Test connection" not in new.text
    )
    token = csrf_from(new.text)
    form = {
        "csrf_token": token,
        "name": "Keycloak",
        "enabled": "on",
        "default_role": "viewer",
        "mapping": "",
        "cfg_discovery_url": "https://sso.example/realms/x/.well-known/openid-configuration",
        "cfg_client_id": "statora",
    }
    bad = await client.post(
        "/admin/settings/auth/new/oidc", data={**form, "mapping": "no equals sign"}, headers=submit
    )
    assert bad.status_code == 200 and "alert-danger" in bad.text and "HX-Redirect" not in bad.headers

    created = await client.post("/admin/settings/auth/new/oidc", data=form, headers=submit)
    target = created.headers["HX-Redirect"]
    provider_id = re.fullmatch(r"/admin/settings/auth\?open=(\d+)", target).group(1)
    # The list reopens the new provider's settings, which show the callback URL to copy.
    reopened = (await client.get(target)).text
    assert (
        f'href="/admin/settings/auth/{provider_id}" class="btn btn-sm" data-modal data-autoopen' in reopened
    )

    edit = (await client.get(f"/admin/settings/auth/{provider_id}", headers=load)).text
    assert f"/auth/oidc/{provider_id}/callback" in edit and "Test connection" in edit
    assert 'form="modal-delete-form"' in edit and 'type="button" class="btn" hx-post' in edit
    saved = await client.post(
        f"/admin/settings/auth/{provider_id}", data={**form, "name": "SSO"}, headers=submit
    )
    assert saved.headers["HX-Redirect"] == "/admin/settings/auth"
    assert "SSO" in (await client.get("/admin/settings/auth")).text
    assert (
        "<html" in (await client.get(f"/admin/settings/auth/{provider_id}")).text
    )  # still a page without the modal


async def test_hide_local_sign_in_form(client, auth):
    await login(client)
    token = csrf_from((await client.get("/admin/settings/auth")).text)
    toggle = "/admin/settings/auth/local-form"

    # Without an enabled provider the form can't be hidden: nobody could sign in.
    refused = await client.post(toggle, data={"csrf_token": token, "hide": "1"})
    assert refused.status_code == 303
    assert "Enable an authentication provider first" in (await client.get("/admin/settings/auth")).text
    client.cookies.clear()
    assert 'id="username"' in (await client.get("/login")).text

    oidc = {
        "name": "SSO",
        "type": "oidc",
        "config": {
            "client_id": "statora",
            "discovery_url": "https://sso.example/.well-known/openid-configuration",
        },
    }
    provider = (await client.post("/api/v1/auth-providers", json=oidc, headers=auth)).json()
    await login(client)
    token = csrf_from((await client.get("/admin/settings/auth")).text)  # new session, new token
    await client.post(toggle, data={"csrf_token": token, "hide": "1"})
    settings = (await client.get("/admin/settings/auth")).text
    assert "The sign-in page only shows your providers" in settings and "/login?local=1" in settings

    client.cookies.clear()
    hidden = (await client.get("/login")).text
    assert 'id="username"' not in hidden and "Sign in with SSO" in hidden and ">or<" not in hidden
    # The way back in: the form is still there on request, and local accounts still work.
    fallback = await client.get("/login?local=1")
    assert 'id="username"' in fallback.text
    signed_in = await client.post(
        "/login",
        data={
            "username": "admin",
            "password": "password123",
            "csrf_token": csrf_from(fallback.text),
            "next": "/admin",
        },
    )
    assert signed_in.status_code == 303 and signed_in.headers["location"] == "/admin"

    # Disabling the last provider brings the form back by itself.
    await client.patch(f"/api/v1/auth-providers/{provider['id']}", json={"enabled": False}, headers=auth)
    client.cookies.clear()
    assert 'id="username"' in (await client.get("/login")).text

    # LDAP accounts use the same form, so it stays while an LDAP provider is enabled.
    await client.patch(f"/api/v1/auth-providers/{provider['id']}", json={"enabled": True}, headers=auth)
    ldap = {
        "name": "AD",
        "type": "ldap",
        "config": {"server_uri": "ldap://ad.example", "bind_dn_template": "uid={username},dc=example"},
    }
    assert (await client.post("/api/v1/auth-providers", json=ldap, headers=auth)).status_code == 201
    assert 'id="username"' in (await client.get("/login")).text

    await login(client)
    token = csrf_from((await client.get("/admin/settings/auth")).text)
    await client.post(toggle, data={"csrf_token": token, "hide": "0"})
    assert "The local sign-in form is shown again" in (await client.get("/admin/settings/auth")).text


async def test_uploaded_logo_concurrent_uploads_and_deep_svgs(client, auth):
    import asyncio

    same = image_bytes("PNG", (40, 40))
    first, second = await asyncio.gather(
        upload(client, auth, "a.png", same), upload(client, auth, "b.png", same)
    )
    assert first.status_code == second.status_code == 201 and first.json()["ref"] == second.json()["ref"]

    ref = first.json()["ref"]
    await client.post(
        "/api/v1/status-pages", json={"slug": "logo", "title": "Logo", "logo_url": ref}, headers=auth
    )
    assert f'src="/media/{ref[6:]}"' in (await client.get("/s/logo")).text

    deep = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        + b"<g>" * 200
        + b'<rect width="1" height="1"/>'
        + b"</g>" * 200
        + b"</svg>"
    )
    response = await upload(client, auth, "deep.svg", deep, "image/svg+xml")
    assert response.status_code == 422 and "nested" in response.json()["detail"]


async def test_icon_preview_is_validated_on_the_server(client, auth):
    await login(client)
    media_ref = "media:" + "b" * 64
    cases = {
        media_ref: "/media/" + "b" * 64,
        "https://cdn.example/i.png": "https://cdn.example/i.png",
        "fa:brands:github": None,
        "javascript:alert(1)": None,
        "http://cdn.example/i.png": None,
        '"><img src=x onerror=alert(1)>': None,
    }
    for ref, expected in cases.items():
        response = await client.get("/admin/media/preview", params={"ref": ref})
        assert response.status_code == 200 and response.json()["src"] == expected, ref


async def test_pages_overview_shows_status_without_history(client, auth):
    page = (
        await client.post("/api/v1/status-pages", json={"slug": "ov", "title": "Overview"}, headers=auth)
    ).json()
    await client.post(
        "/api/v1/incidents",
        json={"page_id": page["id"], "title": "Down", "impact": "critical", "message": "x"},
        headers=auth,
    )
    await login(client)
    assert "Major outage" in (await client.get("/admin/pages")).text


async def test_first_run_setup_creates_the_initial_admin(client):
    assert (await client.get("/login")).headers["location"] == "/setup"
    page = await client.get("/setup")
    assert page.status_code == 200 and "Create the administrator account" in page.text
    token = csrf_from(page.text)
    form = {"csrf_token": token, "username": "root", "password": "rootpassword"}

    mismatch = await client.post("/setup", data={**form, "password_confirm": "different1"})
    assert mismatch.status_code == 422 and "The passwords don&#39;t match" in mismatch.text
    short = await client.post("/setup", data={**form, "password": "short", "password_confirm": "short"})
    assert short.status_code == 422

    done = await client.post("/setup", data={**form, "password_confirm": "rootpassword"})
    assert done.status_code == 303 and done.headers["location"] == "/admin"
    users = await client.get("/admin/users")
    assert users.status_code == 200 and "initial admin" in users.text

    # Setup is closed once a user exists.
    client.cookies.clear()
    assert (await client.get("/setup")).headers["location"] == "/login"
    again = await client.post("/setup", data={**form, "username": "evil", "password_confirm": "rootpassword"})
    assert again.status_code in (303, 403)
    assert (await login(client, "root", "rootpassword")).status_code == 303


async def test_initial_admin_cant_be_deleted_disabled_or_demoted(client, auth):
    root = await make_user("root", UserRole.ADMIN, is_initial_admin=True)
    await login(client)
    token = csrf_from((await client.get(f"/admin/users/{root.id}/edit")).text)

    await client.post(f"/admin/users/{root.id}/delete", data={"csrf_token": token})
    assert "The initial admin can&#39;t be deleted" in (await client.get("/admin/users")).text
    demote = await client.post(
        f"/admin/users/{root.id}/edit", data={"csrf_token": token, "role": "viewer", "active": "on"}
    )
    assert demote.status_code == 422 and "can&#39;t be demoted or disabled" in demote.text

    api_delete = await client.delete(f"/api/v1/users/{root.id}", headers=auth)
    assert api_delete.status_code == 400 and api_delete.json()["code"] == "initial_admin"
    api_disable = await client.patch(f"/api/v1/users/{root.id}", json={"active": False}, headers=auth)
    assert api_disable.status_code == 400 and api_disable.json()["code"] == "initial_admin"
    assert (await client.get(f"/api/v1/users/{root.id}", headers=auth)).json()["is_initial_admin"] is True


async def test_reset_admin_command(services):
    from statora.cli import _reset_admin

    assert await _reset_admin("newpassword", None) is None  # fresh instance: the web UI's setup does it
    root = await make_user("root", UserRole.VIEWER, is_initial_admin=True, active=False)
    assert await _reset_admin("newpassword", "boss") == "boss"
    async with db.session_scope() as s:
        user = await s.get(User, root.id)
        assert user.username == "boss" and user.role == UserRole.ADMIN and user.active
        assert await authenticate_local(s, "boss", "newpassword") is not None


async def test_reset_admin_restores_a_missing_initial_admin(services):
    # Upgraded instance whose only admin signs in through an identity provider: no initial admin.
    from statora.cli import _reset_admin
    from statora.db.models import AuthProvider, AuthProviderType

    async with db.session_scope() as s:
        provider = AuthProvider(name="SSO", type=AuthProviderType.OIDC)
        s.add(provider)
        await s.flush()
        s.add(User(username="sso", role=UserRole.ADMIN, auth_provider_id=provider.id, external_id="1"))
    with pytest.raises(typer.BadParameter):
        await _reset_admin("newpassword", "sso")  # an external account can't become the initial admin
    assert await _reset_admin("newpassword", None) == "admin"
    async with db.session_scope() as s:
        user = await authenticate_local(s, "admin", "newpassword")
        assert user is not None and user.is_initial_admin and user.role == UserRole.ADMIN

    # An existing local account is promoted rather than duplicated.
    async with db.session_scope() as s:
        await s.execute(update(User).values(is_initial_admin=False))
    viewer = await make_user("ops", UserRole.VIEWER, active=False)
    assert await _reset_admin("otherpassword", "ops") == "ops"
    async with db.session_scope() as s:
        user = await s.get(User, viewer.id)
        assert user.is_initial_admin and user.role == UserRole.ADMIN and user.active
