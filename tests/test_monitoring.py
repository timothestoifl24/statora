import asyncio
import contextlib
from datetime import timedelta

import pytest
from sqlalchemy import select

from statora import cache
from statora.checks import CheckResult
from statora.db.base import utcnow
from statora.db.models import Heartbeat, Maintenance, Monitor, MonitorDailyStat, MonitorStatus, MonitorType
from statora.scheduler import check_monitor_once
from statora.services.monitoring import monitors_in_maintenance, record_result, uptime_days

from .conftest import needs_services

pytestmark = needs_services


async def _monitor(session, **kw) -> Monitor:
    monitor = Monitor(name="m", type=MonitorType.TCP, target="127.0.0.1", config={"port": 9}, retries=1, **kw)
    session.add(monitor)
    await session.commit()
    return monitor


async def test_state_machine_with_retries(session):
    monitor = await _monitor(session)
    await record_result(session, monitor, CheckResult.up(5.0))
    assert monitor.status == MonitorStatus.UP

    beat = await record_result(session, monitor, CheckResult.down("refused"))
    assert beat.status == MonitorStatus.PENDING and monitor.status == MonitorStatus.UP  # within retry budget

    beat = await record_result(session, monitor, CheckResult.down("refused"))
    assert beat.status == MonitorStatus.DOWN and beat.important
    assert monitor.status == MonitorStatus.DOWN

    beat = await record_result(session, monitor, CheckResult.up(5.0))
    assert beat.important and monitor.status == MonitorStatus.UP and monitor.consecutive_failures == 0
    await session.commit()

    stat = await session.scalar(select(MonitorDailyStat).where(MonitorDailyStat.monitor_id == monitor.id))
    assert (stat.up_count, stat.down_count, stat.latency_count) == (3, 1, 2)  # pending counts as up
    assert (await uptime_days(session, [monitor.id], 1))[monitor.id] == 0.75
    assert await cache.get_json(cache.monitor_state_key(monitor.id)) is not None


async def test_status_change_invalidates_page_cache(session):
    monitor = await _monitor(session, status=MonitorStatus.UP)
    await cache.set_json(cache.page_key("x"), {"cached": True})
    await record_result(session, monitor, CheckResult.up(1.0))
    assert await cache.get_json(cache.page_key("x")) is not None  # no change, cache kept
    monitor.retries = 0
    await record_result(session, monitor, CheckResult.down("boom"))
    assert await cache.get_json(cache.page_key("x")) is None


async def test_maintenance_window(session):
    monitor = await _monitor(session)
    now = utcnow()
    session.add(
        Maintenance(
            title="m",
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(minutes=1),
            monitors=[monitor],
        )
    )
    session.add(
        Maintenance(
            title="later",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=2),
            monitors=[monitor],
        )
    )
    await session.commit()
    assert await monitors_in_maintenance(session, now) == {monitor.id}
    assert await monitors_in_maintenance(session, now + timedelta(hours=1)) == set()


async def test_leaving_maintenance_is_a_change_even_when_pending(session):
    monitor = await _monitor(session, status=MonitorStatus.UP)
    await record_result(session, monitor, CheckResult.down("refused"), in_maintenance=True)
    assert monitor.status == MonitorStatus.MAINTENANCE
    monitor.consecutive_failures = 0  # within the retry budget once the window is over
    beat = await record_result(session, monitor, CheckResult.down("refused"))
    assert beat.status == MonitorStatus.PENDING and beat.important
    assert monitor.status == MonitorStatus.PENDING


async def test_check_monitor_once_end_to_end(session):
    monitor = await _monitor(session)
    monitor_id = monitor.id
    await check_monitor_once(monitor_id)  # port 9 on localhost is closed → failure → pending
    session.expire_all()
    beats = (await session.scalars(select(Heartbeat).where(Heartbeat.monitor_id == monitor_id))).all()
    assert len(beats) == 1 and beats[0].status == MonitorStatus.PENDING
    await check_monitor_once(monitor_id)
    session.expire_all()
    assert (await session.get(Monitor, monitor_id)).status == MonitorStatus.DOWN


async def test_scheduler_spreads_out_monitors_starting_together(session, monkeypatch):
    from statora import scheduler as scheduler_module

    sched = scheduler_module.Scheduler()
    delays: dict[int, float] = {}
    monkeypatch.setattr(sched, "_spawn", lambda mid, interval, delay=0.0: delays.__setitem__(mid, delay))
    monitors = [await _monitor(session, interval_s=20) for _ in range(20)]
    await sched.sync()
    assert set(delays) == {m.id for m in monitors}
    assert all(0 <= d <= 20 for d in delays.values()) and len(set(delays.values())) > 1

    # A single monitor (an edit, a resync that found one new monitor) still starts right away.
    delays.clear()
    sched._tasks = {m.id: None for m in monitors}
    sched._intervals = {m.id: 20 for m in monitors}
    extra = await _monitor(session)
    await sched.sync()
    assert delays == {extra.id: 0.0}


async def test_scheduler_sync_follows_database(session, monkeypatch):
    from statora import scheduler as scheduler_module

    async def no_check(monitor_id):
        return None

    monkeypatch.setattr(scheduler_module, "check_monitor_once", no_check)
    sched = scheduler_module.Scheduler()
    a = await _monitor(session)
    b = await _monitor(session, interval_s=30)
    await sched.sync()
    assert set(sched._tasks) == {a.id, b.id}
    first_task = sched._tasks[a.id]

    b.active = False
    a.interval_s = 120
    await session.commit()
    await sched.sync()
    assert set(sched._tasks) == {a.id}
    assert (
        sched._tasks[a.id] is not first_task and sched._intervals[a.id] == 120
    )  # restarted with new interval
    await sched.stop()
    assert not sched._tasks


async def test_scheduler_listener_survives_bad_messages_and_disconnects(services, monkeypatch):
    from statora import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "LOCK_RENEW_INTERVAL", 0.01)
    sched = scheduler_module.Scheduler()
    reloaded, synced, got_new_monitor = [], asyncio.Event(), asyncio.Event()

    async def reload_one(monitor_id):
        reloaded.append(monitor_id)
        if monitor_id == 7:
            got_new_monitor.set()

    async def sync():
        # A monitor created while the catch-up resync runs: its notification must not be lost,
        # so the listener has to be subscribed already.
        await cache.publish_monitors_changed(7)
        synced.set()

    monkeypatch.setattr(sched, "reload_one", reload_one)
    monkeypatch.setattr(sched, "sync", sync)

    real_listen_once, calls = sched._listen_once, []

    async def flaky_listen_once(catch_up=False):
        calls.append(catch_up)
        if len(calls) == 1:
            raise ConnectionError("redis went away")
        await real_listen_once(catch_up)

    monkeypatch.setattr(sched, "_listen_once", flaky_listen_once)
    listener = asyncio.create_task(sched._listen())
    try:
        async with asyncio.timeout(5):
            await synced.wait()  # reconnected, and caught up on what it may have missed
            await got_new_monitor.wait()
            while 42 not in reloaded:
                await cache.get_redis().publish(cache.MONITORS_CHANGED_CHANNEL, "not-a-number")
                await cache.publish_monitors_changed(42)
                await asyncio.sleep(0.05)
    finally:
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener
    assert calls == [False, True] and set(reloaded) == {7, 42}


async def test_scheduler_restarts_when_its_listener_stops(services, monkeypatch):
    from statora import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "LOCK_RENEW_INTERVAL", 0.01)
    sched = scheduler_module.Scheduler()

    async def nothing():
        return None

    async def forever():
        await asyncio.Event().wait()

    monkeypatch.setattr(sched, "sync", nothing)
    monkeypatch.setattr(sched, "_listen", nothing)
    monkeypatch.setattr(sched, "_housekeeping", forever)
    assert await sched._lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="scheduler-listener stopped"):
            async with asyncio.timeout(5):
                await sched._lead()
    finally:
        await sched._lock.release()
    assert not sched.is_leader
