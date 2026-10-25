import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from statora import __version__, cache
from statora.config import get_settings
from statora.db import session as db
from statora.scheduler import Scheduler
from statora.services.crud import ValidationProblem
from statora.web import auth_routes
from statora.web import media as media_routes
from statora.web.admin import router as admin_router
from statora.web.api.v1 import router as api_router
from statora.web.deps import LoginRequired
from statora.web.public import router as public_router
from statora.web.templating import templates

log = logging.getLogger("statora")
STATIC_DIR = Path(__file__).resolve().parent / "static"

API_DESCRIPTION = """
REST API for monitors, status pages, incidents, maintenance windows, users and authentication providers.

**Authentication:** send an API token as `Authorization: Bearer st_…`.
Create one in the web UI (*Profile → API tokens*) or with `POST /api/v1/auth/token` using a local or LDAP account.
Tokens with only the `read` scope can call `GET` endpoints.

Every resource supports list/get/create/update/delete with stable `operationId`s,
which makes the API straightforward to wrap in a Terraform provider.
"""

_ERROR_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


class VersionedStaticFiles(StaticFiles):
    """Fingerprinted URLs (?v=<hash>, see templating.asset) are cached for a year; others revalidate."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if b"v=" in scope.get("query_string", b""):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


def _operation_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db.init_engine()
    cache.init_redis()
    scheduler = Scheduler() if settings.runs_worker else None
    if scheduler:
        scheduler.start()
    app.state.scheduler = scheduler
    log.info("statora %s started (role=%s)", __version__, settings.role)
    try:
        yield
    finally:
        if scheduler:
            await scheduler.stop()
        await cache.close_redis()
        await db.dispose_engine()


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Statora API",
        version=__version__,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="statora_session",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.secure_cookies,
    )

    @app.exception_handler(LoginRequired)
    async def _login_redirect(request: Request, exc: LoginRequired):
        if request.headers.get("HX-Request"):
            return PlainTextResponse("Login required", status_code=401, headers={"HX-Redirect": "/login"})
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if _is_api(request):
            code = getattr(exc, "code", None) or _ERROR_CODES.get(exc.status_code, "error")
            return JSONResponse({"detail": exc.detail, "code": code}, exc.status_code, headers=exc.headers)
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError):
        errors = [{k: v for k, v in e.items() if k != "ctx"} for e in exc.errors()]
        return JSONResponse({"detail": errors, "code": "validation_error"}, 422)

    @app.exception_handler(ValidationError)
    async def _model_validation(request: Request, exc: ValidationError):
        errors = [{k: v for k, v in e.items() if k not in ("ctx", "url")} for e in exc.errors()]
        return JSONResponse({"detail": errors, "code": "validation_error"}, 422)

    @app.exception_handler(ValidationProblem)
    async def _validation_problem(request: Request, exc: ValidationProblem):
        return JSONResponse({"detail": str(exc), "code": "invalid_reference"}, 422)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        checks = {}
        try:
            async with db.get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
        try:
            await cache.get_redis().ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"
        scheduler = getattr(app.state, "scheduler", None)
        checks["scheduler"] = (
            "leader" if scheduler and scheduler.is_leader else ("standby" if scheduler else "off")
        )
        healthy = checks["database"] == "ok" and checks["redis"] == "ok"
        return JSONResponse({"status": "ok" if healthy else "degraded", **checks}, 200 if healthy else 503)

    # Swagger UI / ReDoc served from bundled assets so the image works without internet access.
    @app.get("/api/docs", include_in_schema=False)
    async def swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_js_url="/static/vendor/swagger-ui-bundle.js",
            swagger_css_url="/static/vendor/swagger-ui.css",
            swagger_favicon_url="/static/brand/favicon.svg",
            swagger_ui_parameters={"persistAuthorization": True},
        )

    @app.get("/api/redoc", include_in_schema=False)
    async def redoc():
        return get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - ReDoc",
            redoc_js_url="/static/vendor/redoc.standalone.js",
            redoc_favicon_url="/static/brand/favicon.svg",
            with_google_fonts=False,
        )

    app.mount("/static", VersionedStaticFiles(directory=STATIC_DIR), name="static")
    if settings.runs_web:
        app.include_router(api_router)
        app.include_router(auth_routes.router)
        app.include_router(admin_router)
        app.include_router(media_routes.router)
        app.include_router(public_router)
    return app
