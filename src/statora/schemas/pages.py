from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from statora.db.models import HistoryResolution, IncidentImpact, IncidentStatus
from statora.schemas.common import ImageRef, check_link

Slug = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
Color = Field(pattern=r"^#[0-9a-fA-F]{6}$")

# ITSM references (incident / change tickets). Links must be http(s) so they can't carry javascript: URLs.
TicketNumber = Annotated[
    str | None, Field(default=None, max_length=100, description="Ticket number in your ITSM tool")
]
TicketUrl = Annotated[
    str | None,
    Field(
        default=None,
        max_length=2048,
        pattern=r"^https?://\S+$",
        description="Link to the ticket or documentation",
    ),
    AfterValidator(check_link),
]


class StatusPageItemIn(BaseModel):
    monitor_id: int
    display_name: str | None = Field(default=None, max_length=150)


class StatusPageItemRead(StatusPageItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class StatusPageGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    items: list[StatusPageItemIn] = Field(default_factory=list, description="Monitors in display order")


class StatusPageGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    position: int
    items: list[StatusPageItemRead]


class StatusPageBase(BaseModel):
    slug: str = Slug
    title: str = Field(min_length=1, max_length=150)
    description: str | None = None
    logo_url: ImageRef = None
    favicon: ImageRef = None
    accent_color: str = Field(default="#1f6feb", pattern=r"^#[0-9a-fA-F]{6}$")
    footer_text: str | None = None
    published: bool = True
    is_default: bool = False
    show_powered_by: bool = Field(default=True, description='Show "Powered by Statora" in the page footer')
    history_resolution: HistoryResolution = Field(
        default=HistoryResolution.DAY,
        description="Uptime bars per minute (last 2 hours), per hour (last 5 days) or per day (last 120 days)",
    )


class StatusPageCreate(StatusPageBase):
    groups: list[StatusPageGroupIn] = Field(
        default_factory=list, description="Component groups in display order"
    )


class StatusPageUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    logo_url: ImageRef = None
    favicon: ImageRef = None
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    footer_text: str | None = None
    published: bool | None = None
    is_default: bool | None = None
    show_powered_by: bool | None = None
    history_resolution: HistoryResolution | None = None
    groups: list[StatusPageGroupIn] | None = Field(
        default=None, description="When given, replaces all groups and their items"
    )


class StatusPageRead(StatusPageBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # Stored values are returned as they are: pages saved before the stricter URL rules (e.g. an
    # http logo) must stay readable. The rules apply when a value is written.
    logo_url: str | None = None
    favicon: str | None = None
    groups: list[StatusPageGroupRead]
    created_at: datetime
    updated_at: datetime


class IncidentUpdateIn(BaseModel):
    status: IncidentStatus
    body: str = Field(min_length=1)


class IncidentUpdateRead(IncidentUpdateIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class IncidentCreate(BaseModel):
    page_id: int
    title: str = Field(min_length=1, max_length=255)
    impact: IncidentImpact = IncidentImpact.MINOR
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    message: str = Field(min_length=1, description="Body of the first incident update")
    monitor_ids: list[int] = Field(default_factory=list, description="Affected monitors")
    started_at: datetime | None = None
    ticket_number: TicketNumber = None
    ticket_url: TicketUrl = None


class IncidentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    impact: IncidentImpact | None = None
    monitor_ids: list[int] | None = None
    ticket_number: TicketNumber = None
    ticket_url: TicketUrl = None


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    page_id: int
    title: str
    impact: IncidentImpact
    status: IncidentStatus
    started_at: datetime
    resolved_at: datetime | None
    monitor_ids: list[int]
    ticket_number: str | None
    ticket_url: str | None
    updates: list[IncidentUpdateRead]
    created_at: datetime
    updated_at: datetime


class MaintenanceBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str | None = None
    starts_at: datetime
    ends_at: datetime
    monitor_ids: list[int] = Field(default_factory=list)
    page_ids: list[int] = Field(default_factory=list)
    change_number: TicketNumber = None
    change_url: TicketUrl = None

    @model_validator(mode="after")
    def _check_window(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class MaintenanceCreate(MaintenanceBase):
    pass


class MaintenancePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    monitor_ids: list[int] | None = None
    page_ids: list[int] | None = None
    change_number: TicketNumber = None
    change_url: TicketUrl = None


class MaintenanceRead(MaintenanceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
