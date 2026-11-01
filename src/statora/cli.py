"""`statora` command line: database setup, demo data and running the server."""

import asyncio
import os
from datetime import timedelta
from pathlib import Path

import typer
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from statora.config import PLACEHOLDER_SECRET_KEYS, get_settings

app = typer.Typer(help="Self-hosted monitoring and status pages.", no_args_is_help=True)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def run_migrations() -> None:
    command.upgrade(_alembic_config(), "head")


@app.command()
def migrate() -> None:
    """Apply database migrations."""
    run_migrations()
    typer.secho("Database is up to date.", fg="green")


async def _reset_admin(password: str, username: str | None) -> str | None:
    """Reset the initial admin's password (and optionally its username).

    An instance upgraded from before the first-run setup may have no initial admin, for example
    when only identity-provider admins are left. Then the local account named `username` (default
    "admin") becomes the initial admin, created if needed, so the operator can always get back in.
    Returns None on a fresh instance, where the web UI's setup creates the account instead.
    """
    from statora.auth.passwords import hash_password
    from statora.auth.service import initial_admin, needs_setup
    from statora.db.models import User, UserRole
    from statora.db.session import dispose_engine, session_scope

    try:
        async with session_scope() as session:
            if await needs_setup(session):
                return None
            admin = await initial_admin(session)
            if admin is None:
                username = username or "admin"
                admin = await session.scalar(
                    select(User).where(func.lower(User.username) == username.lower())
                )
                if admin is not None and not admin.is_local:
                    raise typer.BadParameter(f"{username!r} signs in through an identity provider")
                if admin is None:
                    admin = User(username=username)
                    session.add(admin)
                admin.is_initial_admin = True
            elif username and username.lower() != admin.username.lower():
                taken = await session.scalar(
                    select(User.id).where(func.lower(User.username) == username.lower())
                )
                if taken:
                    raise typer.BadParameter(f"Username {username!r} is taken")
            if username:
                admin.username = username
            admin.password_hash = hash_password(password)
            admin.role = UserRole.ADMIN
            admin.active = True
            return admin.username
    finally:
        await dispose_engine()


@app.command("reset-admin")
def reset_admin(
    password: str = typer.Option(..., prompt="New password", hide_input=True, confirmation_prompt=True),
    username: str | None = typer.Option(
        None, help="Rename the initial admin; without one, the local account to make it (default: admin)"
    ),
) -> None:
    """Reset the initial admin's password and re-enable it (the account from the first-run setup)."""
    if len(password) < 8:
        raise typer.BadParameter("Password must be at least 8 characters")
    name = asyncio.run(_reset_admin(password, username))
    if name is None:
        typer.secho("No users yet. Open the web UI to create the admin account.", fg="yellow", err=True)
        raise typer.Exit(1)
    typer.secho(f"Admin {name!r} reset.", fg="green")


async def _seed() -> bool:
    from statora.db.base import utcnow
    from statora.db.models import (
        Incident,
        IncidentImpact,
        IncidentStatus,
        IncidentUpdate,
        Maintenance,
        Monitor,
        MonitorType,
        StatusPage,
        StatusPageGroup,
        StatusPageItem,
    )
    from statora.db.session import dispose_engine, session_scope

    try:
        async with session_scope() as session:
            if await session.scalar(select(StatusPage.id).where(StatusPage.slug == "demo")):
                return False
            now = utcnow()
            website = Monitor(
                name="Example website",
                type=MonitorType.HTTP,
                target="https://example.com",
                interval_s=60,
                retries=1,
                config={"expected_status": ["200-299"], "keyword": "Example Domain"},
            )
            api = Monitor(
                name="HTTPBin API",
                type=MonitorType.HTTP,
                target="https://httpbin.org/status/200",
                interval_s=60,
                retries=1,
                config={"degraded_threshold_ms": 1500},
            )
            dns_tcp = Monitor(
                name="Cloudflare DNS (TCP 53)",
                type=MonitorType.TCP,
                target="1.1.1.1",
                interval_s=60,
                config={"port": 53},
            )
            ping = Monitor(
                name="Google DNS (ping)",
                type=MonitorType.PING,
                target="8.8.8.8",
                interval_s=60,
                config={"count": 3},
            )
            dns = Monitor(
                name="example.com A record",
                type=MonitorType.DNS,
                target="example.com",
                interval_s=300,
                config={"record_type": "A"},
            )
            broken = Monitor(
                name="Intentionally broken",
                type=MonitorType.TCP,
                target="127.0.0.1",
                interval_s=30,
                timeout_s=3,
                retries=2,
                config={"port": 9},
            )
            for monitor in (website, api, dns_tcp, ping, dns, broken):
                monitor.members = []
            # Groups: a stack (all members needed) and a redundancy group (one of two is enough).
            platform = Monitor(
                name="Web platform (stack)",
                type=MonitorType.GROUP,
                target="",
                interval_s=30,
                config={"mode": "stack", "min_up": 1, "degraded_on_member_failure": True},
                members=[website, api],
            )
            resolvers = Monitor(
                name="Public DNS (redundant)",
                type=MonitorType.GROUP,
                target="",
                interval_s=30,
                config={"mode": "redundancy", "min_up": 1, "degraded_on_member_failure": True},
                members=[dns_tcp, ping],
            )
            monitors = [website, api, dns_tcp, ping, dns, broken, platform, resolvers]
            session.add_all(monitors)
            await session.flush()

            page = StatusPage(
                slug="demo",
                title="Demo Status",
                description="Live status of the demo services. This page was created by `statora init --seed`.",
                is_default=True,
                groups=[
                    StatusPageGroup(
                        name="Platform",
                        position=0,
                        items=[
                            StatusPageItem(monitor_id=platform.id, position=0, display_name="Web platform"),
                            StatusPageItem(monitor_id=resolvers.id, position=1, display_name="DNS service"),
                        ],
                    ),
                    StatusPageGroup(
                        name="Websites",
                        position=1,
                        items=[
                            StatusPageItem(monitor_id=website.id, position=0, display_name="Website"),
                            StatusPageItem(monitor_id=api.id, position=1, display_name="Public API"),
                        ],
                    ),
                    StatusPageGroup(
                        name="Infrastructure",
                        position=2,
                        items=[
                            StatusPageItem(monitor_id=dns_tcp.id, position=0, display_name="DNS resolver"),
                            StatusPageItem(monitor_id=ping.id, position=1, display_name="Network"),
                            StatusPageItem(monitor_id=dns.id, position=2, display_name="DNS records"),
                            StatusPageItem(monitor_id=broken.id, position=3, display_name="Legacy service"),
                        ],
                    ),
                ],
            )
            session.add(page)
            await session.flush()

            session.add(
                Incident(
                    page_id=page.id,
                    title="Elevated API error rates",
                    impact=IncidentImpact.MINOR,
                    status=IncidentStatus.RESOLVED,
                    started_at=now - timedelta(days=2, hours=1),
                    resolved_at=now - timedelta(days=2),
                    monitors=[api],
                    updates=[
                        IncidentUpdate(
                            status=IncidentStatus.INVESTIGATING,
                            created_at=now - timedelta(days=2, hours=1),
                            body="We are investigating increased error rates on the public API.",
                        ),
                        IncidentUpdate(
                            status=IncidentStatus.RESOLVED,
                            created_at=now - timedelta(days=2),
                            body="A faulty deployment was rolled back. Error rates are back to normal.",
                        ),
                    ],
                )
            )
            start = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
            session.add(
                Maintenance(
                    title="Database upgrade",
                    body="Planned upgrade of the primary database. Brief interruptions possible.",
                    starts_at=start,
                    ends_at=start + timedelta(hours=2),
                    monitors=[api],
                    pages=[page],
                )
            )
            return True
    finally:
        await dispose_engine()


async def _notify_scheduler() -> None:
    """Tell a running scheduler to pick up monitors created from the CLI (best effort)."""
    from statora import cache

    try:
        await cache.publish_monitors_changed()
    except Exception:
        pass  # not running / Redis unavailable: the scheduler resyncs periodically anyway
    finally:
        await cache.close_redis()


@app.command()
def seed() -> None:
    """Add demo monitors, a demo status page (/s/demo), an incident and a maintenance window."""
    created = asyncio.run(_seed())
    asyncio.run(_notify_scheduler())
    typer.secho(
        "Demo data created." if created else "Demo data already present.", fg="green" if created else "yellow"
    )


@app.command()
def init(
    seed_data: bool = typer.Option(True, "--seed/--no-seed", help="Add demo monitors and a demo status page"),
) -> None:
    """Set up a fresh instance: migrate and (optionally) add demo data."""
    typer.echo(f"Database: {get_settings().database_url.rsplit('@', 1)[-1]}")
    run_migrations()
    typer.secho("✓ Migrations applied", fg="green")

    if seed_data:
        asyncio.run(_seed())
        asyncio.run(_notify_scheduler())
        typer.secho("✓ Demo data ready (status page at /s/demo)", fg="green")
    typer.echo("\nNext: statora dev   →  http://localhost:8000 (create the admin account on first visit)")


def _uvicorn(reload: bool, host: str, port: int, workers: int = 1) -> None:
    import uvicorn

    uvicorn.run(
        "statora.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(Path(__file__).resolve().parent)] if reload else None,
        workers=None if reload else workers,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


@app.command()
def dev(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Run the web app and the checker with auto-reload (development)."""
    _uvicorn(reload=True, host=host, port=port)


@app.command()
def serve(
    migrate_db: bool = typer.Option(True, "--migrate/--no-migrate", help="Apply migrations before starting"),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
) -> None:
    """Production entrypoint."""
    settings = get_settings()
    if settings.secret_key in PLACEHOLDER_SECRET_KEYS:
        # A publicly known key lets anyone forge a session cookie (and sign in as any user) and
        # decrypt the stored provider and database secrets, so refuse to run with one.
        typer.secho(
            "STATORA_SECRET_KEY is not set (it still has the example value). Set it to a long random value, "
            'for example the output of: python -c "import secrets; print(secrets.token_urlsafe(48))"',
            fg="red",
            err=True,
        )
        raise typer.Exit(1)
    if migrate_db:
        run_migrations()
    _uvicorn(reload=False, host=host or settings.host, port=port or settings.port)


if __name__ == "__main__":
    app()
