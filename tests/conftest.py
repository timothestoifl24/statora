"""Test fixtures.

Integration tests need PostgreSQL and Redis; by default they use the dev services from
docker-compose.dev.yml (a separate `statora_test` database and Redis DB 15). Override with
STATORA_TEST_DATABASE_URL / STATORA_TEST_REDIS_URL.
"""

import asyncio
import os
import socket
from urllib.parse import urlsplit

TEST_DB_URL = os.environ.get(
    "STATORA_TEST_DATABASE_URL",
    "postgresql+asyncpg://statora:statora@localhost:5432/statora_test",
)
TEST_REDIS_URL = os.environ.get("STATORA_TEST_REDIS_URL", "redis://localhost:6379/15")

# Must be set before statora.config is imported anywhere.
os.environ.update(
    STATORA_DATABASE_URL=TEST_DB_URL,
    STATORA_REDIS_URL=TEST_REDIS_URL,
    STATORA_SECRET_KEY="test-secret-key-0123456789",
    STATORA_ROLE="web",
    STATORA_BASE_URL="http://statora.test",  # python3-saml rejects dot-less hosts,
)

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from sqlalchemy import text  # noqa: E402

from statora import cache  # noqa: E402
from statora.auth.passwords import hash_password  # noqa: E402
from statora.auth.tokens import issue_token  # noqa: E402
from statora.cli import _alembic_config  # noqa: E402
from statora.db import session as db  # noqa: E402
from statora.db.base import Base  # noqa: E402
from statora.db.models import TokenScope, User, UserRole  # noqa: E402


def _reachable(url: str, default_port: int) -> bool:
    parts = urlsplit(url.replace("+asyncpg", ""))
    try:
        with socket.create_connection((parts.hostname, parts.port or default_port), timeout=1):
            return True
    except OSError:
        return False


SERVICES_UP = _reachable(TEST_DB_URL, 5432) and _reachable(TEST_REDIS_URL, 6379)
needs_services = pytest.mark.skipif(not SERVICES_UP, reason="PostgreSQL/Redis not reachable")


async def _ensure_database() -> None:
    parts = urlsplit(TEST_DB_URL.replace("+asyncpg", ""))
    name = parts.path.lstrip("/")
    admin_dsn = parts._replace(path="/postgres").geturl()
    conn = await asyncpg.connect(admin_dsn)
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_db():
    if not SERVICES_UP:
        pytest.skip("PostgreSQL/Redis not reachable")
    asyncio.run(_ensure_database())
    cfg = _alembic_config()
    cfg.attributes["database_url"] = TEST_DB_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return TEST_DB_URL


@pytest.fixture
async def services(migrated_db):
    db.init_engine(TEST_DB_URL)
    redis = cache.init_redis(TEST_REDIS_URL)
    await redis.flushdb()
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with db.get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield
    await cache.close_redis()
    await db.dispose_engine()


@pytest.fixture
async def session(services):
    async with db.sessionmaker()() as s:
        yield s


@pytest.fixture
def app(services):
    from statora.main import create_app

    return create_app()


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def make_user(username: str, role: UserRole, password: str = "password123", **kw) -> User:
    async with db.session_scope() as s:
        user = User(username=username, role=role, password_hash=hash_password(password), **kw)
        s.add(user)
    return user


async def make_token(user: User, scopes=(TokenScope.READ, TokenScope.WRITE), **kw) -> str:
    async with db.session_scope() as s:
        user = await s.get(User, user.id)
        issued = await issue_token(s, user, "test", list(scopes), **kw)
    return issued.plaintext


@pytest.fixture
async def admin_token(services) -> str:
    return await make_token(await make_user("admin", UserRole.ADMIN))


@pytest.fixture
def auth(admin_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}
