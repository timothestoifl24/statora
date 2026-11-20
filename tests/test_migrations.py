import asyncio
import json
from urllib.parse import urlsplit

import asyncpg
from alembic import command

from statora.auth import crypto
from statora.cli import _alembic_config

from .conftest import TEST_DB_URL, needs_services

pytestmark = needs_services


def _query(sql: str, *args):
    async def run():
        conn = await asyncpg.connect(urlsplit(TEST_DB_URL.replace("+asyncpg", "")).geturl())
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    return asyncio.run(run())


def test_http_monitor_credentials_are_encrypted_on_upgrade(migrated_db):
    cfg = _alembic_config()
    cfg.attributes["database_url"] = migrated_db
    command.downgrade(cfg, "6a1f3c8e2b47")
    try:
        _query("TRUNCATE monitors RESTART IDENTITY CASCADE")
        config = {"headers": {"Authorization": "Bearer s3cret"}, "body": "a=1", "method": "POST"}
        _query(
            "INSERT INTO monitors (name, type, target, interval_s, timeout_s, retries, config, active, status,"
            " consecutive_failures) VALUES ('API', 'http', 'https://api.example.org', 60, 10, 0, $1::jsonb,"
            " true, 'pending', 0)",
            json.dumps(config),
        )
        command.upgrade(cfg, "head")
        stored = json.loads(_query("SELECT config FROM monitors")[0]["config"])
        assert crypto.is_encrypted(stored["headers"]["Authorization"]) and crypto.is_encrypted(stored["body"])
        assert crypto.decrypt(stored["headers"]["Authorization"]) == "Bearer s3cret"
        assert stored["method"] == "POST"

        command.downgrade(cfg, "6a1f3c8e2b47")
        assert json.loads(_query("SELECT config FROM monitors")[0]["config"]) == config
    finally:
        command.upgrade(cfg, "head")
        _query("TRUNCATE monitors RESTART IDENTITY CASCADE")
