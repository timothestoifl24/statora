import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from statora.db.models import MonitorStatus, MonitorType

_STATUS_RANGE = re.compile(r"^\d{3}(-\d{3})?$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Config(_Strict):
    # Responses slower than this are reported as "degraded" instead of "up".
    degraded_threshold_ms: int | None = Field(default=None, ge=1)


class HttpConfig(_Config):
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] = "GET"
    expected_status: list[str] = Field(default_factory=lambda: ["200-299"])
    keyword: str | None = None
    invert_keyword: bool = False
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    follow_redirects: bool = True
    verify_tls: bool = True

    @field_validator("expected_status")
    @classmethod
    def _check_ranges(cls, value: list[str]) -> list[str]:
        for item in value:
            if not _STATUS_RANGE.match(item):
                raise ValueError(f"invalid status code or range: {item!r} (use e.g. '200' or '200-299')")
        return value

    def status_ok(self, code: int) -> bool:
        for item in self.expected_status:
            low, _, high = item.partition("-")
            if int(low) <= code <= int(high or low):
                return True
        return False


class TcpConfig(_Config):
    port: int = Field(ge=1, le=65535)


class PingConfig(_Config):
    count: int = Field(default=3, ge=1, le=10)


class DnsConfig(_Config):
    record_type: Literal["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "CAA"] = "A"
    resolver: str | None = Field(default=None, description="Nameserver IP; system resolver when empty")
    expected_value: str | None = Field(
        default=None, description="Monitor is down unless one of the answers contains this value"
    )


SQL_DEFAULT_PORTS = {"postgresql": 5432, "mysql": 3306, "mssql": 1433, "oracle": 1521}
SQL_ENGINE_LABELS = {
    "postgresql": "PostgreSQL",
    "mysql": "MySQL / MariaDB",
    "mssql": "Microsoft SQL Server",
    "oracle": "Oracle",
}


class SqlConfig(_Config):
    engine: Literal["postgresql", "mysql", "mssql", "oracle"]
    port: int | None = Field(
        default=None, ge=1, le=65535, description="Default port of the engine when empty"
    )
    database: str | None = Field(default=None, description="Database name; the service name for Oracle")
    username: str | None = None
    password: str | None = Field(default=None, description="Write-only; stored encrypted and never returned")
    query: str | None = Field(
        default=None, description="Read-only query to run; SELECT 1 (Oracle: SELECT 1 FROM DUAL) when empty"
    )
    expected_value: str | None = Field(
        default=None, description="Compared with the first column of the first row, as text"
    )
    match: Literal["equals", "contains"] = "equals"
    min_rows: int | None = Field(default=None, ge=0, le=1000, description="Down when fewer rows are returned")
    tls: bool = False
    verify_tls: bool = True

    @model_validator(mode="after")
    def _oracle_select_only(self) -> "SqlConfig":
        # Oracle commits DDL implicitly and has no read-only session, so only queries are accepted.
        if self.engine == "oracle" and self.query and not re.match(r"^\s*(SELECT|WITH)\b", self.query, re.I):
            raise ValueError("Oracle queries must start with SELECT or WITH")
        return self

    @property
    def effective_port(self) -> int:
        return self.port or SQL_DEFAULT_PORTS[self.engine]

    @property
    def effective_query(self) -> str:
        if self.query and self.query.strip():
            return self.query.strip().rstrip(";").strip()
        return "SELECT 1 FROM DUAL" if self.engine == "oracle" else "SELECT 1"


class GroupConfig(_Strict):
    mode: Literal["stack", "redundancy"] = Field(
        default="stack",
        description="stack: every member must be healthy; redundancy: at least min_up members must be up",
    )
    min_up: int = Field(default=1, ge=1, description="Redundancy only: members that must be up")
    degraded_on_member_failure: bool = Field(
        default=True, description="Redundancy only: report 'degraded' while some members are down"
    )


CONFIG_MODELS: dict[MonitorType, type[_Strict]] = {
    MonitorType.HTTP: HttpConfig,
    MonitorType.TCP: TcpConfig,
    MonitorType.PING: PingConfig,
    MonitorType.DNS: DnsConfig,
    MonitorType.SQL: SqlConfig,
    MonitorType.GROUP: GroupConfig,
}

# Config fields that are stored encrypted and never returned by the API or shown in the UI.
SECRET_FIELDS: dict[MonitorType, tuple[str, ...]] = {MonitorType.SQL: ("password",)}


def redact_config(monitor_type: MonitorType | str, config: dict[str, Any] | None) -> dict[str, Any]:
    """A copy of the config with secret fields set to None."""
    data = dict(config or {})
    for name in SECRET_FIELDS.get(MonitorType(monitor_type), ()):
        if name in data:
            data[name] = None
    return data


def parse_config(monitor_type: MonitorType | str, config: dict[str, Any] | None) -> _Strict:
    return CONFIG_MODELS[MonitorType(monitor_type)].model_validate(config or {})


Interval = Annotated[int, Field(ge=10, le=86_400, description="Seconds between checks")]
Timeout = Annotated[int, Field(ge=1, le=120, description="Seconds before a check fails")]
Retries = Annotated[int, Field(ge=0, le=10, description="Extra failures tolerated before going down")]


class MonitorBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    type: MonitorType
    target: str = Field(default="", max_length=2048, description="Not used by group monitors")
    interval_s: Interval = 60
    timeout_s: Timeout = 10
    retries: Retries = 0
    config: dict[str, Any] = Field(default_factory=dict)
    member_ids: list[int] = Field(default_factory=list, description="Group monitors only: member monitor ids")
    active: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "MonitorBase":
        self.config = parse_config(self.type, self.config).model_dump(exclude_none=False)
        self.member_ids = list(dict.fromkeys(self.member_ids))  # dedupe, keep order
        if self.type == MonitorType.GROUP:
            self.target = ""
            if not self.member_ids:
                raise ValueError("A group needs at least one member monitor")
            if self.config["mode"] == "redundancy" and self.config["min_up"] > len(self.member_ids):
                raise ValueError("min_up can't be larger than the number of members")
        else:
            if self.member_ids:
                raise ValueError("member_ids is only allowed for group monitors")
            if not self.target.strip():
                raise ValueError("target is required")
        if self.type == MonitorType.HTTP and not self.target.startswith(("http://", "https://")):
            raise ValueError("HTTP monitors need a target starting with http:// or https://")
        if self.timeout_s >= self.interval_s:
            raise ValueError("timeout_s must be smaller than interval_s")
        return self


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    """Partial update; omitted fields keep their current value."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    target: str | None = Field(default=None, max_length=2048)
    interval_s: Interval | None = None
    timeout_s: Timeout | None = None
    retries: Retries | None = None
    config: dict[str, Any] | None = None
    member_ids: list[int] | None = None
    active: bool | None = None


class MonitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    type: MonitorType
    target: str
    interval_s: int
    timeout_s: int
    retries: int
    config: dict[str, Any]
    member_ids: list[int]
    active: bool
    status: MonitorStatus
    status_changed_at: datetime | None
    last_checked_at: datetime | None
    last_latency_ms: float | None
    last_message: str | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _hide_secrets(self) -> "MonitorRead":
        self.config = redact_config(self.type, self.config)
        return self


class HeartbeatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    status: MonitorStatus
    latency_ms: float | None
    message: str | None
    important: bool


class UptimeRead(BaseModel):
    monitor_id: int
    uptime_24h: float | None
    uptime_7d: float | None
    uptime_30d: float | None
    uptime_90d: float | None
    avg_latency_24h_ms: float | None
