"""SQL monitors: config rules, result evaluation and checks against real databases.

PostgreSQL uses the test database. MySQL/MariaDB, SQL Server and Oracle run when their test
servers are reachable (compose profile "sql", or the services in CI); override the connection with
STATORA_TEST_MYSQL_URL, STATORA_TEST_MSSQL_URL and STATORA_TEST_ORACLE_URL.
"""

import os
import socket
from urllib.parse import unquote, urlsplit

import pytest

from statora.checks import CheckTarget, run_check
from statora.checks.sql import MAX_ROWS, describe_rows, evaluate_rows
from statora.db.models import MonitorStatus, MonitorType
from statora.schemas.monitor import SqlConfig, parse_config, redact_config

from .conftest import TEST_DB_URL

SERVERS = {
    "postgresql": TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://"),
    "mysql": os.environ.get("STATORA_TEST_MYSQL_URL", "mysql://statora:statora@localhost:3306/statora"),
    "mssql": os.environ.get("STATORA_TEST_MSSQL_URL", "mssql://sa:Statora-dev-1@localhost:1433"),
    "oracle": os.environ.get("STATORA_TEST_ORACLE_URL", "oracle://statora:statora@localhost:1521/FREEPDB1"),
}
SLOW_QUERIES = {
    "postgresql": "SELECT pg_sleep(5)",
    "mysql": "SELECT SLEEP(5)",
    "mssql": "WAITFOR DELAY '00:00:05'; SELECT 1",
    "oracle": "SELECT COUNT(*) FROM all_objects a, all_objects b, all_objects c",
}


def _server(engine: str) -> dict:
    parts = urlsplit(SERVERS[engine])
    return {
        "host": parts.hostname,
        "engine": engine,
        "port": parts.port,
        "username": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "database": parts.path.lstrip("/") or None,
    }


def _reachable(engine: str) -> bool:
    server = _server(engine)
    try:
        with socket.create_connection((server["host"], server["port"]), timeout=1):
            return True
    except OSError:
        return False


def sql_target(engine: str, timeout_s: int = 5, **config) -> CheckTarget:
    server = _server(engine)
    host = server.pop("host")
    cfg = parse_config(MonitorType.SQL, {**server, **config}).model_dump()
    return CheckTarget(id=1, type=MonitorType.SQL, target=host, timeout_s=timeout_s, config=cfg)


engines = pytest.mark.parametrize(
    "engine",
    [
        pytest.param(e, marks=pytest.mark.skipif(not _reachable(e), reason=f"{e} test server not running"))
        for e in SERVERS
    ],
)


# ---------------------------------------------------------------- config and evaluation


def test_config_defaults_and_oracle_guard():
    cfg = SqlConfig(engine="mssql")
    assert cfg.effective_port == 1433 and cfg.effective_query == "SELECT 1"
    assert SqlConfig(engine="oracle").effective_query == "SELECT 1 FROM DUAL"
    assert SqlConfig(engine="mysql", port=3307, query=" SELECT 2; ").effective_query == "SELECT 2"
    SqlConfig(engine="oracle", query="with t as (select 1 x from dual) select x from t")
    with pytest.raises(ValueError, match="SELECT or WITH"):
        SqlConfig(engine="oracle", query="DROP TABLE users")
    with pytest.raises(ValueError):
        SqlConfig(engine="sqlite")


def test_redact_config():
    config = {"engine": "postgresql", "password": "enc:secret"}
    assert redact_config(MonitorType.SQL, config)["password"] is None
    assert config["password"] == "enc:secret"  # the original is left alone
    assert redact_config(MonitorType.HTTP, {"keyword": "x"}) == {"keyword": "x"}


def test_evaluate_rows():
    cfg = SqlConfig(engine="postgresql", expected_value="ok")
    assert evaluate_rows(cfg, [("ok",)]) is None
    assert evaluate_rows(cfg, [("fail",)]) == "Expected 'ok', got 'fail'"
    assert "no rows" in evaluate_rows(cfg, [])
    contains = SqlConfig(engine="postgresql", expected_value="ok", match="contains")
    assert evaluate_rows(contains, [("all ok",)]) is None
    assert evaluate_rows(SqlConfig(engine="postgresql", expected_value="NULL"), [(None,)]) is None
    assert evaluate_rows(SqlConfig(engine="postgresql", expected_value="true"), [(True,)]) is None
    assert (
        evaluate_rows(SqlConfig(engine="postgresql", min_rows=2), [(1,)]) == "Expected at least 2 rows, got 1"
    )
    assert describe_rows([(1,), (2,)]) == "2 rows · first value: 1"
    assert describe_rows([]) == "0 rows"
    assert describe_rows([(i,) for i in range(MAX_ROWS)]).startswith(f"{MAX_ROWS}+ rows")


async def test_unreachable_server_is_down():
    target = CheckTarget(
        id=1,
        type=MonitorType.SQL,
        target="127.0.0.1",
        timeout_s=2,
        config={"engine": "postgresql", "port": 1},
    )
    result = await run_check(target)
    assert result.status == MonitorStatus.DOWN and result.message.startswith("PostgreSQL: ")


# ---------------------------------------------------------------- real databases


@engines
async def test_query_and_expectations(engine):
    up = await run_check(sql_target(engine))
    assert up.status == MonitorStatus.UP, up.message
    assert up.message == "1 row · first value: 1" and up.latency_ms is not None

    mismatch = await run_check(sql_target(engine, expected_value="2"))
    assert mismatch.status == MonitorStatus.DOWN and mismatch.message == "Expected '2', got '1'"

    too_few = await run_check(sql_target(engine, min_rows=2))
    assert too_few.status == MonitorStatus.DOWN and "at least 2 rows" in too_few.message

    # Connecting alone takes longer than 1 ms.
    degraded = await run_check(sql_target(engine, degraded_threshold_ms=1))
    assert degraded.status == MonitorStatus.DEGRADED, degraded.message


@engines
async def test_wrong_password_and_timeout(engine):
    wrong = await run_check(sql_target(engine, password="definitely-wrong"))
    assert wrong.status == MonitorStatus.DOWN
    assert "definitely-wrong" not in wrong.message

    slow = await run_check(sql_target(engine, timeout_s=2, query=SLOW_QUERIES[engine]))
    assert slow.status == MonitorStatus.DOWN and "no answer within 2s" in slow.message


@engines
async def test_queries_cannot_change_data(engine):
    if engine == "oracle":
        with pytest.raises(ValueError):
            sql_target(engine, query="CREATE TABLE statora_probe (a INT)")
        return
    create = "CREATE TABLE statora_probe (a INT)" + ("; SELECT 1" if engine == "mssql" else "")
    await run_check(sql_target(engine, query=create))
    # PostgreSQL and MySQL reject the statement; SQL Server runs it but the transaction is rolled back.
    table = {
        "postgresql": "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'statora_probe'",
        "mysql": "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'statora_probe'",
        "mssql": "SELECT COUNT(*) FROM sys.tables WHERE name = 'statora_probe'",
    }[engine]
    result = await run_check(sql_target(engine, query=table, expected_value="0"))
    assert result.status == MonitorStatus.UP, result.message
