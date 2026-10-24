"""SQL checks: connect to a database, run a read-only query and compare the result.

The query runs in a read-only transaction where the engine supports one and is always rolled back.
Each engine function returns the fetched rows (at most MAX_ROWS) as sequences of column values.
The whole check runs under asyncio.timeout; driver_timeout also ends connects and queries on the
driver side (and the SQL Server thread, which can't be cancelled).
"""

import asyncio
import functools
import ssl
import threading
import time
from collections.abc import Sequence
from typing import Any

from statora.auth import crypto
from statora.schemas.monitor import SQL_ENGINE_LABELS, SqlConfig

from .base import CheckResult, CheckTarget

MAX_ROWS = 1000
Rows = list[Sequence[Any]]


def _ssl_context(cfg: SqlConfig) -> ssl.SSLContext | None:
    if not cfg.tls:
        return None
    context = ssl.create_default_context()
    if not cfg.verify_tls:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


async def _postgresql(host: str, cfg: SqlConfig, password: str | None, driver_timeout: float) -> Rows:
    import asyncpg

    conn = await asyncpg.connect(
        host=host,
        port=cfg.effective_port,
        user=cfg.username,
        password=password,
        database=cfg.database,
        ssl=_ssl_context(cfg) or False,
        timeout=driver_timeout,
        command_timeout=driver_timeout,
    )
    try:
        transaction = conn.transaction(readonly=True)
        await transaction.start()
        try:
            rows: Rows = []
            async for row in conn.cursor(cfg.effective_query, prefetch=100):
                rows.append(tuple(row.values()))
                if len(rows) >= MAX_ROWS:
                    break
            return rows
        finally:
            await transaction.rollback()
    finally:
        try:
            await asyncio.wait_for(conn.close(), 2)
        except Exception:
            conn.terminate()


async def _mysql(host: str, cfg: SqlConfig, password: str | None, driver_timeout: float) -> Rows:
    import aiomysql

    conn = await aiomysql.connect(
        host=host,
        port=cfg.effective_port,
        user=cfg.username,
        password=password or "",
        db=cfg.database,
        ssl=_ssl_context(cfg),
        connect_timeout=driver_timeout,
        autocommit=False,
    )
    try:
        async with conn.cursor() as cursor:
            # Session-wide, so statements with an implicit commit (DDL) are rejected too.
            await cursor.execute("SET SESSION TRANSACTION READ ONLY")
            await cursor.execute("START TRANSACTION READ ONLY")
            await cursor.execute(cfg.effective_query)
            rows = list(await cursor.fetchmany(MAX_ROWS)) if cursor.description else []
        await conn.rollback()
        return rows
    finally:
        conn.close()


_mssql_tls = threading.local()


@functools.cache
def _patch_pytds_tls() -> None:
    """Let python-tds skip certificate checks, which it has no option for.

    pytds.connect() builds its TLS context with pytds.tls.create_context() in the calling thread,
    so a thread-local flag decides per connection whether the certificate is verified.
    """
    import OpenSSL.SSL
    import pytds.tls

    original = pytds.tls.create_context

    def create_context(cafile: str) -> OpenSSL.SSL.Context:
        context = original(cafile)
        if getattr(_mssql_tls, "insecure", False):
            context.set_verify(OpenSSL.SSL.VERIFY_NONE, lambda *_: True)
        return context

    pytds.tls.create_context = create_context


def _mssql_sync(host: str, cfg: SqlConfig, password: str | None, driver_timeout: float) -> Rows:
    import pytds

    tls: dict[str, Any] = {}
    if cfg.tls:
        # python-tds encrypts the connection when a CA file is given (via pyOpenSSL).
        _patch_pytds_tls()
        tls = {"cafile": ssl.get_default_verify_paths().cafile, "validate_host": cfg.verify_tls}
    _mssql_tls.insecure = cfg.tls and not cfg.verify_tls
    with pytds.connect(
        dsn=host,
        port=cfg.effective_port,
        database=cfg.database,
        user=cfg.username,
        password=password,
        login_timeout=driver_timeout,
        timeout=driver_timeout,
        autocommit=False,
        appname="Statora",
        **tls,
    ) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(cfg.effective_query)
                return list(cursor.fetchmany(MAX_ROWS)) if cursor.description else []
        finally:
            conn.rollback()


async def _mssql(host: str, cfg: SqlConfig, password: str | None, driver_timeout: float) -> Rows:
    # python-tds is synchronous; its own timeouts end the thread if the check times out first.
    return await asyncio.to_thread(_mssql_sync, host, cfg, password, driver_timeout)


async def _oracle(host: str, cfg: SqlConfig, password: str | None, driver_timeout: float) -> Rows:
    import oracledb

    conn = await oracledb.connect_async(
        user=cfg.username,
        password=password,
        host=host,
        port=cfg.effective_port,
        service_name=cfg.database,
        protocol="tcps" if cfg.tls else "tcp",
        ssl_context=_ssl_context(cfg),
        ssl_server_dn_match=cfg.verify_tls,
        tcp_connect_timeout=driver_timeout,
        retry_count=0,
    )
    try:
        await conn.execute("SET TRANSACTION READ ONLY")
        with conn.cursor() as cursor:
            await cursor.execute(cfg.effective_query)
            rows = list(await cursor.fetchmany(MAX_ROWS)) if cursor.description else []
        await conn.rollback()
        return rows
    finally:
        await conn.close()


ENGINES = {"postgresql": _postgresql, "mysql": _mysql, "mssql": _mssql, "oracle": _oracle}


def _text(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, bytes | bytearray):
        return value.hex()
    return str(value)


def _short(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _error_message(exc: Exception) -> str:
    # PyMySQL errors carry (code, message) as arguments, python-tds errors (message, details).
    args = exc.args
    if len(args) == 2 and isinstance(args[0], int) and isinstance(args[1], str):
        text = f"{args[1]} ({args[0]})"
    elif args and isinstance(args[0], str):
        text = args[0].strip()
    else:
        text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def evaluate_rows(cfg: SqlConfig, rows: Rows) -> str | None:
    """None when the rows meet the expectations, otherwise the reason the check failed."""
    if cfg.min_rows is not None and len(rows) < cfg.min_rows:
        return f"Expected at least {cfg.min_rows} rows, got {len(rows)}"
    if cfg.expected_value is not None:
        if not rows or not rows[0]:
            return f"Expected {cfg.expected_value!r}, but the query returned no rows"
        actual = _text(rows[0][0])
        ok = actual == cfg.expected_value if cfg.match == "equals" else cfg.expected_value in actual
        if not ok:
            wording = "" if cfg.match == "equals" else "a value containing "
            return f"Expected {wording}{cfg.expected_value!r}, got {_short(actual)!r}"
    return None


def describe_rows(rows: Rows) -> str:
    count = (
        f"{MAX_ROWS}+ rows" if len(rows) >= MAX_ROWS else f"{len(rows)} row{'s' if len(rows) != 1 else ''}"
    )
    if rows and rows[0]:
        return f"{count} · first value: {_short(_text(rows[0][0]))}"
    return count


async def check_sql(target: CheckTarget) -> CheckResult:
    cfg = SqlConfig.model_validate(target.config)
    label = SQL_ENGINE_LABELS[cfg.engine]
    password = crypto.decrypt(cfg.password) if cfg.password else None
    start = time.perf_counter()
    try:
        async with asyncio.timeout(target.timeout_s):
            rows = await ENGINES[cfg.engine](target.target, cfg, password, float(target.timeout_s))
    except TimeoutError:
        return CheckResult.down(f"{label}: no answer within {target.timeout_s}s")
    except Exception as exc:  # driver errors: authentication, unknown database, SQL errors, …
        return CheckResult.down(f"{label}: {_short(_error_message(exc), 200)}")
    latency = (time.perf_counter() - start) * 1000
    if problem := evaluate_rows(cfg, rows):
        return CheckResult.down(problem, latency)
    return CheckResult.up(latency, describe_rows(rows), cfg.degraded_threshold_ms)
