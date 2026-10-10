"""Pure logic: retries, overall status, uptime buckets, role mapping, secrets."""

from types import SimpleNamespace

from statora.auth import crypto
from statora.auth.providers.base import load_config, public_config, store_config
from statora.auth.service import role_for_groups
from statora.checks import CheckResult
from statora.db.models import (
    AuthProvider,
    AuthProviderType,
    IncidentImpact,
    MonitorDailyStat,
    MonitorStatus,
    UserRole,
)
from statora.services.monitoring import resolve_status
from statora.services.status import Overall, day_level, overall_status

DOWN = CheckResult.down("nope")
UP = CheckResult.up(10.0)


def monitor(status=MonitorStatus.UP, failures=0, retries=2):
    return SimpleNamespace(status=status, consecutive_failures=failures, retries=retries)


def test_retries_turn_failures_into_pending_then_down():
    assert resolve_status(monitor(failures=0), DOWN, False) == MonitorStatus.PENDING
    assert resolve_status(monitor(failures=1), DOWN, False) == MonitorStatus.PENDING
    assert resolve_status(monitor(failures=2), DOWN, False) == MonitorStatus.DOWN
    assert resolve_status(monitor(retries=0), DOWN, False) == MonitorStatus.DOWN


def test_down_stays_down_and_recovers_immediately():
    assert resolve_status(monitor(MonitorStatus.DOWN, failures=0), DOWN, False) == MonitorStatus.DOWN
    assert resolve_status(monitor(MonitorStatus.DOWN, failures=5), UP, False) == MonitorStatus.UP


def test_maintenance_overrides_result():
    assert resolve_status(monitor(), DOWN, True) == MonitorStatus.MAINTENANCE


def test_overall_status():
    up, down, deg = MonitorStatus.UP, MonitorStatus.DOWN, MonitorStatus.DEGRADED
    assert overall_status([up, up], []) == Overall.OPERATIONAL
    assert overall_status([up, deg], []) == Overall.DEGRADED
    assert overall_status([up, down], []) == Overall.PARTIAL_OUTAGE
    assert overall_status([down, down], []) == Overall.MAJOR_OUTAGE
    assert overall_status([up, MonitorStatus.MAINTENANCE], []) == Overall.MAINTENANCE
    assert overall_status([up], [IncidentImpact.CRITICAL]) == Overall.MAJOR_OUTAGE
    assert overall_status([down, up], [IncidentImpact.MINOR]) == Overall.PARTIAL_OUTAGE
    assert overall_status([], []) == Overall.OPERATIONAL


def stat(**counts):
    return MonitorDailyStat(
        up_count=counts.get("up", 0),
        degraded_count=counts.get("degraded", 0),
        down_count=counts.get("down", 0),
        maintenance_count=counts.get("maintenance", 0),
    )


def test_day_level_buckets():
    assert day_level(None) == "none"
    assert day_level(stat(up=100)) == "up"
    assert day_level(stat(up=80, degraded=20)) == "degraded"
    assert day_level(stat(up=99, down=1)) == "partial"
    assert day_level(stat(up=50, down=50)) == "down"
    assert day_level(stat(maintenance=10)) == "maintenance"


def test_role_for_groups_picks_highest_case_insensitive():
    provider = AuthProvider(
        default_role=UserRole.VIEWER,
        group_role_mapping={"Ops": "editor", "cn=admins,dc=x": "admin"},
    )
    assert role_for_groups(provider, []) == UserRole.VIEWER
    assert role_for_groups(provider, ["ops"]) == UserRole.EDITOR
    assert role_for_groups(provider, ["ops", "CN=admins,DC=x"]) == UserRole.ADMIN


def test_secrets_are_encrypted_hidden_and_preserved():
    config = {
        "server_uri": "ldap://dir",
        "bind_dn": "cn=svc",
        "bind_password": "s3cret",
        "user_search_base": "dc=example",
    }
    stored = store_config(AuthProviderType.LDAP, config)
    assert crypto.is_encrypted(stored["bind_password"])
    assert "s3cret" not in str(stored)

    provider = AuthProvider(type=AuthProviderType.LDAP, config=stored)
    assert public_config(provider)["bind_password"] is None
    assert load_config(provider).bind_password == "s3cret"

    # Updating without a password keeps the stored one.
    updated = store_config(AuthProviderType.LDAP, {**config, "bind_password": None}, stored)
    assert updated["bind_password"] == stored["bind_password"]
