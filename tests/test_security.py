"""Security hardening: response headers, NUL bytes, URL validation, secret key, upload limits."""

import pytest
from pydantic import TypeAdapter, ValidationError

from statora.schemas.common import IconRef, ImageRef, LinkUrl

from .conftest import needs_services


@needs_services
async def test_security_headers(client):
    admin = await client.get("/login")
    csp = admin.headers["content-security-policy"]
    assert admin.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp and "base-uri 'self'" in csp and "form-action 'self'" in csp
    assert admin.headers["x-content-type-options"] == "nosniff"
    assert admin.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert (
        "httponly" in admin.headers["set-cookie"].lower()
        and "samesite=lax" in admin.headers["set-cookie"].lower()
    )

    public = await client.get("/")
    # Status pages may be embedded elsewhere, but still don't load foreign scripts.
    assert "x-frame-options" not in public.headers
    assert "frame-ancestors" not in public.headers["content-security-policy"]
    assert "unsafe-eval" not in public.headers["content-security-policy"]

    docs = await client.get("/api/docs")
    assert (
        "content-security-policy" not in docs.headers and docs.headers["x-content-type-options"] == "nosniff"
    )


@needs_services
@pytest.mark.parametrize("path", ["/s/%00", "/s/a%00b", "/media/%00", "/admin?x=%00", "/login?next=%00"])
async def test_nul_bytes_in_urls_are_rejected(client, path):
    assert (await client.get(path)).status_code == 400


@needs_services
async def test_nul_bytes_in_bodies_are_rejected(client, auth):
    json_nul = await client.post(
        "/api/v1/monitors",
        content=b'{"name": "a\\u0000b", "type": "http", "target": "https://example.com"}',
        headers={**auth, "Content-Type": "application/json"},
    )
    assert json_nul.status_code == 400
    form_nul = await client.post(
        "/login",
        content=b"username=a%00b&password=x",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert form_nul.status_code == 400
    # "%00" is just text inside JSON.
    fine = await client.post(
        "/api/v1/monitors",
        json={"name": "Discount 100%00", "type": "http", "target": "https://example.com"},
        headers=auth,
    )
    assert fine.status_code == 201


@needs_services
async def test_oversized_upload_is_refused_before_parsing(client, auth):
    response = await client.post(
        "/api/v1/media",
        content=b"x" * (600 * 1024),
        headers={**auth, "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "https://user:pass@evil.example",
        "https://user@evil.example",
        "//evil.example/x",
        "https:/\\evil.example",
        "https://evil .example",
        "https://evil.example/\tx",
        "http://",
        "http://example.com:99999",
        "ftp://example.com/file",
    ],
)
def test_bad_links_are_rejected(value):
    with pytest.raises(ValidationError):
        TypeAdapter(LinkUrl).validate_python(value)


@pytest.mark.parametrize(
    "value", ["https://example.com", "http://10.0.0.5:3000/d/x?y=1#z", "https://grafana.example.com/"]
)
def test_good_links_are_accepted(value):
    assert TypeAdapter(LinkUrl).validate_python(value) == value


def test_image_references_need_https_or_an_upload():
    images = TypeAdapter(ImageRef)
    assert images.validate_python("https://cdn.example/logo.svg")
    assert images.validate_python("media:" + "a" * 64)
    for bad in (
        "http://cdn.example/logo.svg",
        "media:../../etc/passwd",
        "media:" + "A" * 64,
        "data:image/png;base64,AAAA",
    ):
        with pytest.raises(ValidationError):
            images.validate_python(bad)
    icons = TypeAdapter(IconRef)
    assert icons.validate_python("fa:brands:github")
    for bad in ("fa:solid:../../x", "fa:solid:not-an-icon", "fa:evil:github", "javascript:alert(1)"):
        with pytest.raises(ValidationError):
            icons.validate_python(bad)


def test_serve_refuses_a_placeholder_secret_key(monkeypatch):
    from typer.testing import CliRunner

    from statora import cli
    from statora.config import get_settings

    started = []
    monkeypatch.setattr(cli, "_uvicorn", lambda **kw: started.append(kw))
    monkeypatch.setattr(cli, "run_migrations", lambda: None)
    for placeholder in ("change-me-in-production", "change-me-to-a-long-random-value"):
        monkeypatch.setenv("STATORA_SECRET_KEY", placeholder)
        get_settings.cache_clear()
        result = CliRunner().invoke(cli.app, ["serve", "--no-migrate"])
        assert result.exit_code == 1 and "STATORA_SECRET_KEY" in result.output
    assert not started
    monkeypatch.setenv("STATORA_SECRET_KEY", "a-real-random-key-0123456789abcdef")
    get_settings.cache_clear()
    assert CliRunner().invoke(cli.app, ["serve", "--no-migrate"]).exit_code == 0 and started
    monkeypatch.undo()  # restore the test environment's key before settings are read again
    get_settings.cache_clear()


@needs_services
async def test_large_text_body_is_not_cut_off(client, auth):
    # Bodies over the scanned size must still reach the app complete (the request used to hang).
    description = "x" * (1536 * 1024)
    response = await client.post(
        "/api/v1/status-pages", json={"slug": "big", "title": "Big", "description": description}, headers=auth
    )
    assert response.status_code == 201 and len(response.json()["description"]) == len(description)


@needs_services
async def test_failed_fallback_login_keeps_the_form(client, auth):
    oidc = {
        "name": "SSO",
        "type": "oidc",
        "config": {"client_id": "x", "discovery_url": "https://sso.example/.well-known/openid-configuration"},
    }
    await client.post("/api/v1/auth-providers", json=oidc, headers=auth)
    from .test_ui import csrf_from, login

    await login(client)
    token = csrf_from((await client.get("/admin/settings/auth")).text)
    await client.post("/admin/settings/auth/local-form", data={"csrf_token": token, "hide": "1"})
    client.cookies.clear()

    page = await client.get("/login?local=1")
    assert 'action="/login?local=1"' in page.text
    failed = await client.post(
        "/login?local=1",
        data={"username": "admin", "password": "wrong", "csrf_token": csrf_from(page.text), "next": "/admin"},
    )
    assert failed.status_code == 401 and 'id="username"' in failed.text  # the admin can try again


@needs_services
async def test_saved_legacy_logo_stays_readable(client, auth, session):
    from statora.db.models import StatusPage

    page = (
        await client.post("/api/v1/status-pages", json={"slug": "old", "title": "Old"}, headers=auth)
    ).json()
    stored = await session.get(StatusPage, page["id"])
    stored.logo_url = "http://legacy.example/logo.png"  # saved before the https-only rule
    await session.commit()
    assert (await client.get(f"/api/v1/status-pages/{page['id']}", headers=auth)).json()[
        "logo_url"
    ] == "http://legacy.example/logo.png"
    assert (await client.get("/api/v1/status-pages", headers=auth)).status_code == 200
    # Writes still follow the new rules.
    bad = await client.patch(
        f"/api/v1/status-pages/{page['id']}", json={"logo_url": "http://legacy.example/x.png"}, headers=auth
    )
    assert bad.status_code == 422
