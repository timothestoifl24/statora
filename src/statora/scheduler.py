"""Runs monitor checks on their intervals. Only the replica holding the Redis leader lock runs checks."""

import asyncio
import contextlib
import logging
import time

from sqlalchemy import select

from statora import cache
from statora.checks import CheckTarget, run_check
from statora.config import get_settings
from statora.db.models import Monitor
from statora.db.session import session_scope
from statora.services.groups import evaluate_group, parent_group_ids
from statora.services.monitoring import monitors_in_maintenance, purge_old_heartbeats, record_result

log = logging.getLogger(__name__)

LOCK_RENEW_INTERVAL = 5
# Safety net for changes that bypass pub/sub (CLI, direct DB edits, missed messages).
RESYNC_INTERVAL = 60
HOUSEKEEPING_INTERVAL = 3600
MAX_CONCURRENT_CHECKS = 50


def _snapshot(monitor: Monitor) -> CheckTarget:
    return CheckTarget(
        id=monitor.id,
        type=monitor.type,
        target=monitor.target,
        timeout_s=monitor.timeout_s,
        config=dict(monitor.config or {}),
    )


async def check_monitor_once(monitor_id: int, _seen: frozenset[int] = frozenset()) -> None:
    """Run one check for a monitor and persist the outcome.

    Group monitors are evaluated from their members' stored status. When any monitor changes
    status, the groups containing it are re-evaluated straight away instead of on their next tick.
    """
    async with session_scope() as session:
        monitor = await session.get(Monitor, monitor_id)
        if monitor is None or not monitor.active:
            return
        target = None if monitor.is_group else _snapshot(monitor)
    result = await run_check(target) if target else None
    async with session_scope() as session:
        monitor = await session.get(Monitor, monitor_id, with_for_update=True)
        if monitor is None:
            return
        maintenance = await monitors_in_maintenance(session)
        if result is None:
            result = evaluate_group(monitor.config, monitor.members, maintenance)
        heartbeat = await record_result(session, monitor, result, in_maintenance=monitor_id in maintenance)
        parents = await parent_group_ids(session, monitor_id) if heartbeat.important else []
    seen = _seen | {monitor_id}
    for parent_id in parents:
        if parent_id not in seen:  # loops are rejected on save; this is just a safety net
            await check_monitor_once(parent_id, seen)


class Scheduler:
    def __init__(self) -> None:
        self._lock = cache.LeaderLock()
        self._tasks: dict[int, asyncio.Task] = {}
        self._intervals: dict[int, int] = {}
        self._runner: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
        self.is_leader = False

    def start(self) -> None:
        self._runner = asyncio.create_task(self._run(), name="scheduler")

    async def stop(self) -> None:
        if self._runner:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
        await self._stop_monitors()
        if self.is_leader:
            with contextlib.suppress(Exception):
                await self._lock.release()
        self.is_leader = False

    async def _run(self) -> None:
        while True:
            try:
                if await self._lock.acquire():
                    log.info("Scheduler acquired leadership")
                    self.is_leader = True
                    await self._lead()
                else:
                    await asyncio.sleep(LOCK_RENEW_INTERVAL)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scheduler error; retrying")
                await self._stop_monitors()
                self.is_leader = False
                await asyncio.sleep(LOCK_RENEW_INTERVAL)

    async def _lead(self) -> None:
        await self.sync()
        listener = asyncio.create_task(self._listen())
        housekeeping = asyncio.create_task(self._housekeeping())
        last_sync = time.monotonic()
        try:
            while True:
                await asyncio.sleep(LOCK_RENEW_INTERVAL)
                if not await self._lock.renew():
                    log.warning("Scheduler lost leadership")
                    break
                if time.monotonic() - last_sync >= RESYNC_INTERVAL:
                    await self.sync()
                    last_sync = time.monotonic()
        finally:
            listener.cancel()
            housekeeping.cancel()
            await self._stop_monitors()
            self.is_leader = False

    async def _listen(self) -> None:
        pubsub = cache.get_redis().pubsub()
        await pubsub.subscribe(cache.MONITORS_CHANGED_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = message["data"]
                if data:
                    await self.reload_one(int(data))
                else:
                    await self.sync()
        finally:
            await pubsub.aclose()

    async def _housekeeping(self) -> None:
        while True:
            try:
                async with session_scope() as session:
                    deleted = await purge_old_heartbeats(session, get_settings().heartbeat_retention_days)
                if deleted:
                    log.info("Purged %d old heartbeats", deleted)
            except Exception:
                log.exception("Housekeeping failed")
            await asyncio.sleep(HOUSEKEEPING_INTERVAL)

    async def sync(self) -> None:
        """Make the running tasks match the active monitors (and their intervals) in the database."""
        async with session_scope() as session:
            rows = await session.execute(select(Monitor.id, Monitor.interval_s).where(Monitor.active))
            wanted = dict(rows.all())
        for monitor_id in list(self._tasks):
            if wanted.get(monitor_id) != self._intervals.get(monitor_id):
                self._cancel(monitor_id)
        started = [mid for mid in wanted if mid not in self._tasks]
        for monitor_id in started:
            self._spawn(monitor_id, wanted[monitor_id])
        if started:
            log.info("Scheduling %d monitors (%d new)", len(self._tasks), len(started))

    def _cancel(self, monitor_id: int) -> None:
        task = self._tasks.pop(monitor_id, None)
        self._intervals.pop(monitor_id, None)
        if task:
            task.cancel()

    async def reload_one(self, monitor_id: int) -> None:
        self._cancel(monitor_id)
        async with session_scope() as session:
            monitor = await session.get(Monitor, monitor_id)
            if monitor is not None and monitor.active:
                self._spawn(monitor.id, monitor.interval_s)

    def _spawn(self, monitor_id: int, interval: int) -> None:
        self._intervals[monitor_id] = interval
        self._tasks[monitor_id] = asyncio.create_task(
            self._loop(monitor_id, interval), name=f"monitor-{monitor_id}"
        )

    async def _loop(self, monitor_id: int, interval: int) -> None:
        while True:
            started = time.monotonic()
            try:
                async with self._semaphore:
                    await check_monitor_once(monitor_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Check for monitor %s failed", monitor_id)
            await asyncio.sleep(max(1.0, interval - (time.monotonic() - started)))

    async def _stop_monitors(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        self._intervals.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
