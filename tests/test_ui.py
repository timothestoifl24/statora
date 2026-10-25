import json
import re
from datetime import timedelta

from statora.auth import crypto
from statora.db.base import utcnow
from statora.db.models import Monitor, UserRole

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
    assert 'id="theme-toggle"' in shown.text and "statora-theme" in shown.text

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


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def test_media_upload_validation_and_headers(client, auth):
    ok = await client.post("/api/v1/media", files={"file": ("x.png", PNG, "image/png")}, headers=auth)
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["ref"].startswith("media:") and body["content_type"] == "image/png"
    again = await client.post("/api/v1/media", files={"file": ("y.png", PNG, "image/png")}, headers=auth)
    assert again.json()["ref"] == body["ref"]  # identical files are stored once

    served = await client.get(body["url"])
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert "sandbox" in served.headers["content-security-policy"]
    assert served.headers["x-content-type-options"] == "nosniff"

    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'
    assert (
        await client.post("/api/v1/media", files={"file": ("i.svg", svg)}, headers=auth)
    ).status_code == 201
    rejected = {
        "script.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        "handler.svg": b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>',
        "fake.png": b"<html>not an image</html>",
        "big.png": PNG + b"\x00" * (256 * 1024),
    }
    for name, data in rejected.items():
        response = await client.post("/api/v1/media", files={"file": (name, data, "image/png")}, headers=auth)
        assert response.status_code == 422, name
    assert (await client.get("/media/" + "0" * 64)).status_code == 404


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
