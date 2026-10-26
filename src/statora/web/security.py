"""Security headers for every response."""

from statora.config import get_settings

# Pages still use inline scripts and styles (theme switch, page editor) and htmx evaluates trigger
# filters, so inline code is allowed; everything else is limited to this site. Images may come from
# https because favicons, logos and monitor icons can be external URLs.
_BASE_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'{eval}; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' https: data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'{frames}"
)
ADMIN_POLICY = _BASE_POLICY.format(eval=" 'unsafe-eval'", frames="; frame-ancestors 'none'")
# Status pages may be embedded in other sites, so they don't restrict frame-ancestors.
PUBLIC_POLICY = _BASE_POLICY.format(eval="", frames="")

# Signed-in areas: never shown inside another site's frame (clickjacking).
_PRIVATE_PREFIXES = ("/admin", "/login", "/logout", "/auth/")
# Swagger UI and ReDoc bring their own scripts and workers; they get the generic headers only.
_NO_CSP_PREFIXES = ("/api/docs", "/api/redoc", "/api/openapi.json")


class SecurityHeaders:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path: str = scope["path"]
        private = path.startswith(_PRIVATE_PREFIXES)
        hsts = get_settings().secure_cookies

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {name.lower() for name, _ in headers}

                def add(name: bytes, value: str) -> None:
                    if name not in present:
                        headers.append((name, value.encode()))

                add(b"x-content-type-options", "nosniff")
                add(b"referrer-policy", "strict-origin-when-cross-origin")
                add(b"permissions-policy", "camera=(), microphone=(), geolocation=(), payment=()")
                if private:
                    add(b"x-frame-options", "DENY")
                if not path.startswith(_NO_CSP_PREFIXES):
                    add(b"content-security-policy", ADMIN_POLICY if private else PUBLIC_POLICY)
                if hsts:
                    add(b"strict-transport-security", "max-age=31536000; includeSubDomains")
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RejectNulBytes:
    """400 for requests with NUL characters in the path, query or a text body.

    PostgreSQL can't store NUL in text, so such input would otherwise surface as a server error.
    Multipart uploads are binary and are left alone (images are validated by services/media.py).
    """

    MAX_SCANNED_BODY = 1024 * 1024

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        raw = scope.get("raw_path") or scope["path"].encode()
        query = scope.get("query_string", b"")
        if b"\x00" in scope["path"].encode() or b"%00" in raw.lower() or b"%00" in query or b"\x00" in query:
            return await _bad_request(send)
        content_type = dict(scope["headers"]).get(b"content-type", b"").lower()
        if scope["method"] in ("GET", "HEAD", "OPTIONS") or content_type.startswith(b"multipart/"):
            return await self.app(scope, receive, send)

        # Buffer the (small) text body, check it, then replay it to the app.
        chunks, size, more_body = [], 0, False
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return await self.app(scope, receive, send)
            body = message.get("body", b"")
            size += len(body)
            chunks.append(body)
            more_body = message.get("more_body", False)
            if size > self.MAX_SCANNED_BODY or not more_body:
                break
        body = b"".join(chunks)
        encoded_nul = b"%00" if content_type.startswith(b"application/x-www-form-urlencoded") else b"\\u0000"
        if b"\x00" in body or encoded_nul in body.lower():
            return await _bad_request(send)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                # Anything after the scanned part is passed through unchecked, as it arrives.
                return {"type": "http.request", "body": body, "more_body": more_body}
            return await receive()

        await self.app(scope, replay, send)


async def _bad_request(send) -> None:
    body = b'{"detail":"The request contains a NUL character.","code":"bad_request"}'
    await send(
        {
            "type": "http.response.start",
            "status": 400,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
