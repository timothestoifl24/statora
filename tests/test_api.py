from datetime import timedelta

import pytest
from openapi_spec_validator import validate

from statora.auth import crypto
from statora.db.base import utcnow
from statora.db.models import Monitor, TokenScope, UserRole

from .conftest import make_token, make_user, needs_services

pytestmark = needs_services

HTTP_MONITOR = {"name": "Website", "type": "http", "target": "https://example.org", "interval_s": 60}


async def test_token_from_credentials_then_crud(client):
    await make_user("alice", UserRole.EDITOR, password="alicepassword")
    response = await client.post(
        "/api/v1/auth/token", json={"username": "alice", "password": "alicepassword", "name": "ci"}
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]
    assert token.startswith("st_")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/api/v1/monitors", json=HTTP_MONITOR, headers=headers)
    assert created.status_code == 201, created.text
    monitor = created.json()
    assert monitor["config"]["expected_status"] == ["200-299"]  # defaults filled in

    patched = await client.patch(
        f"/api/v1/monitors/{monitor['id']}", json={"interval_s": 120}, headers=headers
    )
    assert patched.json()["interval_s"] == 120

    listing = await client.get("/api/v1/monitors", params={"name": "Website"}, headers=headers)
    assert listing.json()["total"] == 1

    replaced = await client.put(
        f"/api/v1/monitors/{monitor['id']}",
        json={**HTTP_MONITOR, "type": "tcp", "target": "db.internal", "config": {"port": 5432}},
        headers=headers,
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["type"] == "tcp" and replaced.json()["config"]["port"] == 5432

    for _ in range(2):  # DELETE is idempotent
        assert (await client.delete(f"/api/v1/monitors/{monitor['id']}", headers=headers)).status_code == 204
    missing = await client.get(f"/api/v1/monitors/{monitor['id']}", headers=headers)
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"


async def test_validation_errors(client, auth):
    bad_type_config = {**HTTP_MONITOR, "type": "tcp", "target": "host"}  # tcp needs a port
    response = await client.post("/api/v1/monitors", json=bad_type_config, headers=auth)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"

    timeout = {**HTTP_MONITOR, "timeout_s": 60, "interval_s": 30}
    assert (await client.post("/api/v1/monitors", json=timeout, headers=auth)).status_code == 422


async def test_unauthenticated_and_invalid_tokens(client):
    assert (await client.get("/api/v1/monitors")).json()["code"] == "unauthenticated"
    bad = await client.get("/api/v1/monitors", headers={"Authorization": "Bearer st_nope_nope"})
    assert bad.status_code == 401 and bad.json()["code"] == "invalid_token"


async def test_read_scope_cannot_write(client):
    user = await make_user("bob", UserRole.ADMIN)
    token = await make_token(user, scopes=[TokenScope.READ])
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/monitors", headers=headers)).status_code == 200
    response = await client.post("/api/v1/monitors", json=HTTP_MONITOR, headers=headers)
    assert response.status_code == 403 and response.json()["code"] == "insufficient_scope"


async def test_viewer_role_cannot_write_or_manage_users(client):
    token = await make_token(await make_user("vic", UserRole.VIEWER))
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/monitors", headers=headers)).status_code == 200
    assert (await client.post("/api/v1/monitors", json=HTTP_MONITOR, headers=headers)).status_code == 403
    assert (await client.get("/api/v1/users", headers=headers)).status_code == 403


async def test_expired_and_revoked_tokens(client):
    user = await make_user("carol", UserRole.EDITOR)
    expired = await make_token(user, expires_at=utcnow() - timedelta(minutes=1))
    assert (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})).status_code == 401

    token = await make_token(user)
    headers = {"Authorization": f"Bearer {token}"}
    tokens = (await client.get("/api/v1/tokens", headers=headers)).json()
    assert len(tokens) == 2 and all("token" not in t for t in tokens)
    current = next(t for t in tokens if token.startswith(f"st_{t['token_prefix']}_"))
    assert (await client.delete(f"/api/v1/tokens/{current['id']}", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/me", headers=headers)).status_code == 401


async def test_login_rate_limit(client):
    await make_user("dave", UserRole.VIEWER)
    codes = [
        (await client.post("/api/v1/auth/token", json={"username": "dave", "password": "wrong"})).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429


async def test_user_management(client, auth):
    created = await client.post(
        "/api/v1/users", json={"username": "erin", "password": "erinpassword", "role": "editor"}, headers=auth
    )
    assert created.status_code == 201
    assert "password" not in created.json() and "password_hash" not in created.json()
    dup = await client.post(
        "/api/v1/users", json={"username": "ERIN", "password": "erinpassword"}, headers=auth
    )
    assert dup.status_code == 409

    me = (await client.get("/api/v1/me", headers=auth)).json()
    demote = await client.patch(f"/api/v1/users/{me['id']}", json={"role": "viewer"}, headers=auth)
    assert demote.status_code == 400 and demote.json()["code"] == "self_lockout"


async def test_status_page_incident_and_maintenance_flow(client, auth):
    monitor = (await client.post("/api/v1/monitors", json=HTTP_MONITOR, headers=auth)).json()
    page = await client.post(
        "/api/v1/status-pages",
        json={
            "slug": "main",
            "title": "Main",
            "groups": [{"name": "Web", "items": [{"monitor_id": monitor["id"]}]}],
        },
        headers=auth,
    )
    assert page.status_code == 201, page.text
    page = page.json()
    assert page["groups"][0]["items"][0]["monitor_id"] == monitor["id"]

    dup = await client.post("/api/v1/status-pages", json={"slug": "main", "title": "Dup"}, headers=auth)
    assert dup.status_code == 422 and dup.json()["code"] == "invalid_reference"
    bad_ref = await client.patch(
        f"/api/v1/status-pages/{page['id']}",
        json={"groups": [{"name": "X", "items": [{"monitor_id": 9999}]}]},
        headers=auth,
    )
    assert bad_ref.status_code == 422

    summary = (await client.get("/api/v1/public/pages/main/summary")).json()
    assert summary["overall"]["status"] == "operational"

    incident = await client.post(
        "/api/v1/incidents",
        json={
            "page_id": page["id"],
            "title": "Outage",
            "impact": "critical",
            "message": "Looking into it",
            "monitor_ids": [monitor["id"]],
        },
        headers=auth,
    )
    assert incident.status_code == 201, incident.text
    incident = incident.json()
    # The incident invalidated the cached summary.
    summary = (await client.get("/api/v1/public/pages/main/summary")).json()
    assert summary["overall"]["status"] == "major_outage"
    assert summary["active_incidents"][0]["title"] == "Outage"

    resolved = await client.post(
        f"/api/v1/incidents/{incident['id']}/updates",
        json={"status": "resolved", "body": "Fixed"},
        headers=auth,
    )
    assert resolved.json()["status"] == "resolved" and resolved.json()["resolved_at"]
    summary = (await client.get("/api/v1/public/pages/main/summary")).json()
    assert summary["overall"]["status"] == "operational" and len(summary["past_incidents"]) == 1

    now = utcnow()
    maintenance = await client.post(
        "/api/v1/maintenances",
        json={
            "title": "Upgrade",
            "starts_at": (now - timedelta(minutes=5)).isoformat(),
            "ends_at": (now + timedelta(hours=1)).isoformat(),
            "monitor_ids": [monitor["id"]],
            "page_ids": [page["id"]],
        },
        headers=auth,
    )
    assert maintenance.status_code == 201, maintenance.text
    summary = (await client.get("/api/v1/public/pages/main/summary")).json()
    assert summary["overall"]["status"] == "maintenance"
    assert summary["groups"][0]["components"][0]["status"] == "maintenance"

    backwards = await client.patch(
        f"/api/v1/maintenances/{maintenance.json()['id']}",
        json={"ends_at": (now - timedelta(hours=1)).isoformat()},
        headers=auth,
    )
    assert backwards.status_code == 422


async def test_unpublished_page_is_hidden(client, auth):
    await client.post(
        "/api/v1/status-pages", json={"slug": "draft", "title": "Draft", "published": False}, headers=auth
    )
    assert (await client.get("/api/v1/public/pages/draft/summary")).status_code == 404
    assert (await client.get("/s/draft")).status_code == 404


async def test_auth_provider_api_hides_secrets(client, auth):
    payload = {
        "name": "Corp LDAP",
        "type": "ldap",
        "config": {
            "server_uri": "ldap://127.0.0.1:1",
            "bind_dn": "cn=svc",
            "bind_password": "hunter22",
            "user_search_base": "dc=corp",
        },
        "group_role_mapping": {"admins": "admin"},
    }
    created = await client.post("/api/v1/auth-providers", json=payload, headers=auth)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["config"]["bind_password"] is None and "hunter22" not in created.text

    test = await client.post(f"/api/v1/auth-providers/{body['id']}/test", headers=auth)
    assert test.status_code == 200 and test.json()["ok"] is False

    invalid = await client.post(
        "/api/v1/auth-providers",
        json={**payload, "name": "x", "config": {"server_uri": "ldap://x"}},
        headers=auth,
    )
    assert invalid.status_code == 422


@pytest.mark.usefixtures("services")
async def test_openapi_is_valid_and_terraform_friendly(app):
    spec = app.openapi()
    validate(spec)
    operation_ids = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            operation_ids.append(op["operationId"])
            if not path.startswith(("/api/v1/public", "/api/v1/auth/token")):
                assert op.get("security") == [{"ApiToken": []}], f"{method} {path} lacks bearer security"
    assert len(operation_ids) == len(set(operation_ids))
    assert {"create_monitor", "get_monitor", "update_monitor", "delete_monitor", "list_monitors"} <= set(
        operation_ids
    )


async def test_itsm_references_on_incidents_and_maintenance(client, auth):
    page = (
        await client.post("/api/v1/status-pages", json={"slug": "itsm", "title": "ITSM"}, headers=auth)
    ).json()
    incident = await client.post(
        "/api/v1/incidents",
        json={
            "page_id": page["id"],
            "title": "Outage",
            "message": "Investigating",
            "ticket_number": "INC0012345",
            "ticket_url": "https://itsm.example.com/INC0012345",
        },
        headers=auth,
    )
    assert incident.status_code == 201, incident.text
    body = incident.json()
    assert (body["ticket_number"], body["ticket_url"]) == (
        "INC0012345",
        "https://itsm.example.com/INC0012345",
    )

    patched = await client.patch(
        f"/api/v1/incidents/{body['id']}", json={"ticket_number": "INC0099999"}, headers=auth
    )
    assert patched.json()["ticket_number"] == "INC0099999"
    assert patched.json()["ticket_url"] == "https://itsm.example.com/INC0012345"  # untouched

    unsafe = await client.patch(
        f"/api/v1/incidents/{body['id']}", json={"ticket_url": "javascript:alert(1)"}, headers=auth
    )
    assert unsafe.status_code == 422

    now = utcnow()
    maintenance = await client.post(
        "/api/v1/maintenances",
        json={
            "title": "Patch",
            "starts_at": (now + timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
            "page_ids": [page["id"]],
            "change_number": "CHG0004567",
            "change_url": "https://itsm.example.com/CHG0004567",
        },
        headers=auth,
    )
    assert maintenance.status_code == 201, maintenance.text
    assert maintenance.json()["change_number"] == "CHG0004567"

    # ITSM references are internal: they never reach the public summary.
    summary = (await client.get("/api/v1/public/pages/itsm/summary")).text
    assert "INC00" not in summary and "CHG0004567" not in summary and "itsm.example.com" not in summary


async def test_sql_monitor_password_is_write_only(client, auth, session):
    payload = {
        "name": "Orders DB",
        "type": "sql",
        "target": "db.internal",
        "config": {"engine": "postgresql", "database": "orders", "username": "probe", "password": "hunter22"},
    }
    created = await client.post("/api/v1/monitors", json=payload, headers=auth)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["config"]["password"] is None and "hunter22" not in created.text
    assert body["config"]["query"] is None and body["config"]["match"] == "equals"

    stored = await session.get(Monitor, body["id"])
    assert crypto.is_encrypted(stored.config["password"])
    assert crypto.decrypt(stored.config["password"]) == "hunter22"
    encrypted = stored.config["password"]

    # Changing other config fields without a password keeps the stored one.
    patched = await client.patch(
        f"/api/v1/monitors/{body['id']}",
        json={"config": {**payload["config"], "password": None, "query": "SELECT 2"}},
        headers=auth,
    )
    assert patched.status_code == 200 and patched.json()["config"]["password"] is None
    await session.refresh(stored)
    assert stored.config["password"] == encrypted and stored.config["query"] == "SELECT 2"

    await client.patch(
        f"/api/v1/monitors/{body['id']}",
        json={"config": {**payload["config"], "password": "n3w"}},
        headers=auth,
    )
    await session.refresh(stored)
    assert crypto.decrypt(stored.config["password"]) == "n3w"

    listed = await client.get("/api/v1/monitors", params={"type": "sql"}, headers=auth)
    assert listed.json()["items"][0]["config"]["password"] is None

    oracle = {**payload, "config": {"engine": "oracle", "query": "DELETE FROM orders"}}
    assert (await client.post("/api/v1/monitors", json=oracle, headers=auth)).status_code == 422
