"""Pure logic: retries, overall status, uptime buckets, role mapping, secrets."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from statora.auth import crypto
from statora.auth.providers.base import load_config, public_config, store_config
from statora.auth.service import role_for_groups
from statora.checks import CheckResult
from statora.db.models import (
    AuthProvider,
    AuthProviderType,
    HistoryResolution,
    IncidentImpact,
    MonitorDailyStat,
    MonitorStatus,
    UserRole,
)
from statora.services.monitoring import resolve_status
from statora.services.status import Counts, Overall, bar_level, bar_starts, build_bars, overall_status

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


def test_bar_level_buckets():
    assert bar_level(None) == "none"
    assert bar_level(stat(up=100)) == "up"
    assert bar_level(stat(up=80, degraded=20)) == "degraded"
    assert bar_level(stat(up=99, down=1)) == "partial"
    assert bar_level(stat(up=50, down=50)) == "down"
    assert bar_level(stat(maintenance=10)) == "maintenance"
    assert bar_level(Counts(up_count=3, down_count=1)) == "down"


NOW = datetime(2026, 10, 24, 14, 7, 30, tzinfo=UTC)


def test_bar_starts_cover_each_window():
    minutes = bar_starts(HistoryResolution.MINUTE, NOW)
    assert len(minutes) == 120 and minutes[-1] == datetime(2026, 10, 24, 14, 7, tzinfo=UTC)
    assert minutes[-1] - minutes[0] == timedelta(minutes=119)  # last 2 hours
    hours = bar_starts(HistoryResolution.HOUR, NOW)
    assert len(hours) == 120 and hours[-1] == datetime(2026, 10, 24, 14, tzinfo=UTC)
    assert hours[-1] - hours[0] == timedelta(hours=119)  # last 5 days
    days = bar_starts(HistoryResolution.DAY, NOW)
    assert len(days) == 120 and days[-1] == datetime(2026, 10, 24, tzinfo=UTC)


def _counts(status, ts, count=1):
    counts = Counts()
    counts.add(status, count, ts)
    return counts


def test_minute_bars_continue_results_between_checks():
    starts = bar_starts(HistoryResolution.MINUTE, NOW)
    at = {minute: starts[-1] - timedelta(minutes=minute) for minute in range(12)}
    # A monitor checking every 5 minutes: checks at -10 (down) and -5 (up) minutes.
    buckets = {
        at[10]: _counts("down", at[10] + timedelta(seconds=5)),
        at[5]: _counts("up", at[5] + timedelta(seconds=5)),
    }
    bars, uptime = build_bars(HistoryResolution.MINUTE, starts, buckets, interval_s=300)
    levels = [bar["level"] for bar in bars[-11:]]
    # -10 down, -9..-6 carried down, -5 up, -4..0 carried up (one interval plus one bar).
    assert levels == ["down"] * 5 + ["up"] * 6
    assert "note" not in bars[-6] and bars[-5]["note"].startswith("no check · last result up")
    assert bars[-12]["level"] == "none"  # before the first check
    assert uptime == 50.0  # only real checks count
    assert bars[-1]["label"] == "24 Oct 14:07 UTC"


def test_carry_forward_stops_after_a_missed_check():
    starts = bar_starts(HistoryResolution.MINUTE, NOW)
    last = starts[-10]
    bars, _ = build_bars(HistoryResolution.MINUTE, starts, {last: _counts("up", last)}, interval_s=60)
    assert [bar["level"] for bar in bars[-10:]] == ["up", "up"] + ["none"] * 8


def test_carry_forward_from_before_the_window_but_not_for_days():
    starts = bar_starts(HistoryResolution.HOUR, NOW)
    before = starts[0] - timedelta(hours=1)
    bars, uptime = build_bars(
        HistoryResolution.HOUR, starts, {before: _counts("degraded", before + timedelta(minutes=50))}, 7200
    )
    assert bars[0]["level"] == "degraded" and uptime is None
    days = bar_starts(HistoryResolution.DAY, NOW)
    bars, _ = build_bars(HistoryResolution.DAY, days, {days[0]: _counts("up", days[0])}, 86_400)
    assert bars[1]["level"] == "none"


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


def test_version_comes_from_build_or_package_metadata(monkeypatch):
    import importlib
    from importlib.metadata import version

    import statora

    monkeypatch.setenv("STATORA_BUILD_VERSION", "9.9.9-beta.7")
    assert importlib.reload(statora).__version__ == "9.9.9-beta.7"

    monkeypatch.delenv("STATORA_BUILD_VERSION")
    assert importlib.reload(statora).__version__ == version("statora")


def test_redirect_targets_stay_on_this_site():
    from statora.web.deps import local_path

    assert local_path("/admin/pages?tab=1") == "/admin/pages?tab=1"
    for target in (
        None,
        "",
        "admin",
        "//evil.example",
        "///evil.example",
        "/\\evil.example",
        "/\t/evil.example",
        "https://evil.example",
        "javascript:alert(1)",
    ):
        assert local_path(target) == "/admin"
