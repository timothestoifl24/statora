from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Column, ForeignKey, Index, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from statora.db.base import Base, TimestampMixin, utcnow

from .auth import JSONType
from .enums import MonitorStatus, MonitorType

# Members of group monitors. A monitor can belong to several groups, and groups can contain groups.
monitor_group_members = Table(
    "monitor_group_members",
    Base.metadata,
    Column("group_id", ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True),
    Column("member_id", ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True, index=True),
)


class Monitor(TimestampMixin, Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[MonitorType] = mapped_column(String(16))
    # URL for http, host for tcp/ping, hostname for dns; empty for groups.
    target: Mapped[str] = mapped_column(String(2048))
    interval_s: Mapped[int] = mapped_column(default=60)
    timeout_s: Mapped[int] = mapped_column(default=10)
    # Consecutive failures required before the monitor is considered down.
    retries: Mapped[int] = mapped_column(default=0)
    # Type-specific options, validated by statora.schemas.monitor.
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    active: Mapped[bool] = mapped_column(default=True)

    # Last known state, persisted so it survives restarts and Redis flushes.
    status: Mapped[MonitorStatus] = mapped_column(String(16), default=MonitorStatus.PENDING)
    status_changed_at: Mapped[datetime | None]
    last_checked_at: Mapped[datetime | None]
    last_latency_ms: Mapped[float | None]
    last_message: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(default=0)

    heartbeats: Mapped[list["Heartbeat"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan", passive_deletes=True
    )
    # Eager-loaded (one level) so group membership is available in async code without lazy loads.
    members: Mapped[list["Monitor"]] = relationship(
        secondary=monitor_group_members,
        primaryjoin=lambda: Monitor.id == monitor_group_members.c.group_id,
        secondaryjoin=lambda: Monitor.id == monitor_group_members.c.member_id,
        lazy="selectin",
        join_depth=1,
        order_by=lambda: Monitor.name,
    )

    @property
    def member_ids(self) -> list[int]:
        return [m.id for m in self.members]

    @property
    def is_group(self) -> bool:
        return self.type == MonitorType.GROUP


class Heartbeat(Base):
    __tablename__ = "heartbeats"
    __table_args__ = (Index("ix_heartbeats_monitor_ts", "monitor_id", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(default=utcnow)
    status: Mapped[MonitorStatus] = mapped_column(String(16))
    latency_ms: Mapped[float | None]
    message: Mapped[str | None] = mapped_column(Text)
    # True when this heartbeat changed the monitor's status (used for event lists).
    important: Mapped[bool] = mapped_column(default=False)

    monitor: Mapped[Monitor] = relationship(back_populates="heartbeats")


class MonitorDailyStat(Base):
    __tablename__ = "monitor_daily_stats"
    __table_args__ = (UniqueConstraint("monitor_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    day: Mapped[date]
    # Pending heartbeats (failing, but still within the retry budget) count as up.
    up_count: Mapped[int] = mapped_column(default=0)
    degraded_count: Mapped[int] = mapped_column(default=0)
    down_count: Mapped[int] = mapped_column(default=0)
    maintenance_count: Mapped[int] = mapped_column(default=0)
    latency_sum_ms: Mapped[float] = mapped_column(default=0.0)
    latency_count: Mapped[int] = mapped_column(default=0)

    @property
    def total(self) -> int:
        return self.up_count + self.degraded_count + self.down_count

    @property
    def uptime(self) -> float | None:
        return (self.up_count + self.degraded_count) / self.total if self.total else None
