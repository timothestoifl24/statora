"""Group monitors: status derived from member monitors (stack or redundancy)."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statora.checks import CheckResult
from statora.db.models import Monitor, MonitorStatus, monitor_group_members
from statora.schemas.monitor import GroupConfig

# Members in these states can serve traffic. "pending" means failing but still within the retry
# budget (or not checked yet), so it doesn't take a member out of service.
AVAILABLE = {MonitorStatus.UP, MonitorStatus.DEGRADED, MonitorStatus.PENDING}


def member_status(member: Monitor, in_maintenance: set[int]) -> MonitorStatus | None:
    """Effective status of a member; None for paused members, which are ignored."""
    if not member.active:
        return None
    if member.id in in_maintenance:
        return MonitorStatus.MAINTENANCE
    return MonitorStatus(member.status)


def evaluate_group(config: dict, members: Iterable[Monitor], in_maintenance: set[int]) -> CheckResult:
    cfg = GroupConfig.model_validate(config)
    statuses = [(m, s) for m in members if (s := member_status(m, in_maintenance)) is not None]
    if not statuses:
        return CheckResult(MonitorStatus.PENDING, message="No active members")

    def names(*wanted: MonitorStatus) -> str:
        return ", ".join(m.name for m, s in statuses if s in wanted)

    down = [m for m, s in statuses if s == MonitorStatus.DOWN]
    maintenance = [m for m, s in statuses if s == MonitorStatus.MAINTENANCE]
    degraded = [m for m, s in statuses if s == MonitorStatus.DEGRADED]
    available = [m for m, s in statuses if s in AVAILABLE]
    total = len(statuses)

    if cfg.mode == "stack":
        if down:
            return CheckResult.down(f"Down: {names(MonitorStatus.DOWN)}")
        if maintenance:
            return CheckResult(
                MonitorStatus.MAINTENANCE, message=f"Maintenance: {names(MonitorStatus.MAINTENANCE)}"
            )
        if degraded:
            return CheckResult(MonitorStatus.DEGRADED, message=f"Degraded: {names(MonitorStatus.DEGRADED)}")
        return CheckResult(MonitorStatus.UP, message=f"All {total} members up")

    # Redundancy: enough members must be available.
    need = min(cfg.min_up, total)
    summary = f"{len(available)}/{total} members up (need {need})"
    if len(available) >= need:
        impaired = down or maintenance or degraded
        if impaired and cfg.degraded_on_member_failure:
            not_ok = names(MonitorStatus.DOWN, MonitorStatus.MAINTENANCE, MonitorStatus.DEGRADED)
            return CheckResult(MonitorStatus.DEGRADED, message=f"{summary}; impaired: {not_ok}")
        return CheckResult(MonitorStatus.UP, message=summary)
    # Not enough capacity: planned maintenance isn't an outage.
    if len(available) + len(maintenance) >= need:
        return CheckResult(
            MonitorStatus.MAINTENANCE, message=f"{summary}; maintenance: {names(MonitorStatus.MAINTENANCE)}"
        )
    return CheckResult.down(f"{summary}; down: {names(MonitorStatus.DOWN)}")


async def parent_group_ids(session: AsyncSession, monitor_id: int) -> list[int]:
    rows = await session.execute(
        select(monitor_group_members.c.group_id)
        .join(Monitor, Monitor.id == monitor_group_members.c.group_id)
        .where(monitor_group_members.c.member_id == monitor_id, Monitor.active)
    )
    return list(rows.scalars())


async def would_create_cycle(session: AsyncSession, group_id: int | None, member_ids: list[int]) -> bool:
    """True if making member_ids members of group_id lets the group (indirectly) contain itself."""
    if group_id is None:
        return False  # a new group has no parents yet, so it can't be part of a loop
    if group_id in member_ids:
        return True
    edges: dict[int, set[int]] = {}
    for parent, child in (await session.execute(select(monitor_group_members))).all():
        if parent != group_id:
            edges.setdefault(parent, set()).add(child)
    stack, seen = list(member_ids), set()
    while stack:
        node = stack.pop()
        if node == group_id:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(edges.get(node, ()))
    return False
