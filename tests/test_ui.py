import re

from statora.auth import crypto
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
            "groups_json": '[{"name": "APIs", "items": [{"monitor_id": 1, "display_name": "Public API"}]}]',
        },
    )
    assert page.status_code == 303
    public = await client.get("/s/public")
    assert public.status_code == 200 and "Public API" in public.text and "#ff0000" in public.text
    assert "5 days ago" in public.text and public.text.count('class="bar ') == 120
    editor = await client.get("/admin/pages/1/edit")
    assert '<option value="hour" selected>' in editor.text


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
