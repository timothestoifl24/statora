from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, Table, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from statora.db.base import Base, TimestampMixin, utcnow

from .enums import HistoryResolution, IncidentImpact, IncidentStatus
from .monitoring import Monitor


class StatusPage(TimestampMixin, Base):
    __tablename__ = "status_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(2048))
    # Browser tab icon: "media:<sha256>" (uploaded) or an http(s) URL.
    favicon: Mapped[str | None] = mapped_column(String(2048))
    accent_color: Mapped[str] = mapped_column(String(7), default="#1f6feb")
    footer_text: Mapped[str | None] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(default=True)
    # The page served at "/" when no slug is given.
    is_default: Mapped[bool] = mapped_column(default=False)
    show_powered_by: Mapped[bool] = mapped_column(default=True, server_default=true())
    # One uptime bar per minute (last 2 hours), hour (last 5 days) or day (last 120 days).
    history_resolution: Mapped[HistoryResolution] = mapped_column(
        String(8), default=HistoryResolution.DAY, server_default=HistoryResolution.DAY.value
    )

    groups: Mapped[list["StatusPageGroup"]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="StatusPageGroup.position",
    )
    incidents: Mapped[list["Incident"]] = relationship(back_populates="page", cascade="all, delete-orphan")


class StatusPageGroup(Base):
    __tablename__ = "status_page_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("status_pages.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    position: Mapped[int] = mapped_column(default=0)

    page: Mapped[StatusPage] = relationship(back_populates="groups")
    items: Mapped[list["StatusPageItem"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="StatusPageItem.position",
    )


class StatusPageItem(Base):
    __tablename__ = "status_page_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("status_page_groups.id", ondelete="CASCADE"), index=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str | None] = mapped_column(String(150))
    position: Mapped[int] = mapped_column(default=0)

    group: Mapped[StatusPageGroup] = relationship(back_populates="items")
    monitor: Mapped[Monitor] = relationship()

    @property
    def label(self) -> str:
        return self.display_name or self.monitor.name


incident_monitors = Table(
    "incident_monitors",
    Base.metadata,
    Column("incident_id", ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True),
    Column("monitor_id", ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True),
)

maintenance_monitors = Table(
    "maintenance_monitors",
    Base.metadata,
    Column("maintenance_id", ForeignKey("maintenances.id", ondelete="CASCADE"), primary_key=True),
    Column("monitor_id", ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True),
)

maintenance_pages = Table(
    "maintenance_pages",
    Base.metadata,
    Column("maintenance_id", ForeignKey("maintenances.id", ondelete="CASCADE"), primary_key=True),
    Column("page_id", ForeignKey("status_pages.id", ondelete="CASCADE"), primary_key=True),
)


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("status_pages.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    impact: Mapped[IncidentImpact] = mapped_column(String(16), default=IncidentImpact.MINOR)
    status: Mapped[IncidentStatus] = mapped_column(String(16), default=IncidentStatus.INVESTIGATING)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None]
    # Reference to the ticket in the ITSM tool (internal; not shown on public pages).
    ticket_number: Mapped[str | None] = mapped_column(String(100))
    ticket_url: Mapped[str | None] = mapped_column(String(2048))

    page: Mapped[StatusPage] = relationship(back_populates="incidents")
    monitors: Mapped[list[Monitor]] = relationship(secondary=incident_monitors)
    updates: Mapped[list["IncidentUpdate"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentUpdate.created_at.desc()",
    )

    @property
    def monitor_ids(self) -> list[int]:
        return [m.id for m in self.monitors]

    @property
    def is_resolved(self) -> bool:
        return self.status == IncidentStatus.RESOLVED


class IncidentUpdate(Base):
    __tablename__ = "incident_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    status: Mapped[IncidentStatus] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="updates")


class Maintenance(TimestampMixin, Base):
    __tablename__ = "maintenances"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    # Change ticket in the ITSM tool (internal; not shown on public pages).
    change_number: Mapped[str | None] = mapped_column(String(100))
    change_url: Mapped[str | None] = mapped_column(String(2048))

    monitors: Mapped[list[Monitor]] = relationship(secondary=maintenance_monitors)
    pages: Mapped[list[StatusPage]] = relationship(secondary=maintenance_pages)

    @property
    def monitor_ids(self) -> list[int]:
        return [m.id for m in self.monitors]

    @property
    def page_ids(self) -> list[int]:
        return [p.id for p in self.pages]

    def is_active(self, at: datetime) -> bool:
        return self.starts_at <= at < self.ends_at
