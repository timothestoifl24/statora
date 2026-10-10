from datetime import timedelta

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
