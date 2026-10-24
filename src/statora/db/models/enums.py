from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    @property
    def level(self) -> int:
        return {"viewer": 0, "editor": 1, "admin": 2}[self.value]


class AuthProviderType(StrEnum):
    LDAP = "ldap"
    SAML = "saml"
    OIDC = "oidc"


class TokenScope(StrEnum):
    READ = "read"
    WRITE = "write"


class MonitorType(StrEnum):
    HTTP = "http"
    TCP = "tcp"
    PING = "ping"
    DNS = "dns"
    SQL = "sql"
    # Status derived from member monitors (stack or redundancy group); no network check.
    GROUP = "group"


class MonitorStatus(StrEnum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    PENDING = "pending"
    MAINTENANCE = "maintenance"


class HistoryResolution(StrEnum):
    """Size of one uptime bar on a status page."""

    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


class IncidentImpact(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
