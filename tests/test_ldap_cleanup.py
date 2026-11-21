"""LDAP connections are closed on every path. Uses a fake ldap3 connection: no server needed."""

from types import SimpleNamespace

import pytest

from statora.auth.providers import ldap
from statora.auth.providers.base import AuthError
from statora.schemas.auth_provider import LdapConfig

SERVICE_DN = "cn=svc,dc=example,dc=org"
USER_DN = "cn=alice,ou=users,dc=example,dc=org"


class _FakeConnection:
    """Stands in for ldap3.Connection. `fail_on` picks the step that goes wrong."""

    fail_on: str = ""
    opened: list["_FakeConnection"] = []

    def __init__(self, server, user=None, password=None, **kw):
        self.user, self.unbound, self.entries = user, False, []
        _FakeConnection.opened.append(self)

    def open(self):
        pass

    def start_tls(self):
        if self.fail_on == "start_tls":
            raise ldap.LDAPException("StartTLS refused")

    def bind(self):
        return not (self.fail_on == "user_bind" and self.user == USER_DN)

    def search(self, base, *args, **kw):
        if self.fail_on == ("service_search" if self.user == SERVICE_DN else "user_search"):
            raise ldap.LDAPException("server went away")
        if self.user == SERVICE_DN:
            # The service account finds exactly one user, so the user's own bind follows.
            self.entries = [SimpleNamespace(entry_dn=USER_DN)]

    def unbind(self):
        self.unbound = True


@pytest.mark.parametrize(
    ("fail_on", "error", "connections"),
    [
        ("service_search", ldap.LDAPException, [SERVICE_DN]),
        ("user_search", ldap.LDAPException, [SERVICE_DN, USER_DN]),
        ("user_bind", AuthError, [SERVICE_DN, USER_DN]),
        ("start_tls", ldap.LDAPException, [SERVICE_DN]),
    ],
)
def test_ldap_connections_are_closed_when_a_step_fails(monkeypatch, fail_on, error, connections):
    monkeypatch.setattr(_FakeConnection, "fail_on", fail_on)
    monkeypatch.setattr(_FakeConnection, "opened", [])
    monkeypatch.setattr(ldap, "Connection", _FakeConnection)
    cfg = LdapConfig.model_validate(
        {
            "server_uri": "ldap://ldap.test",
            "bind_dn": SERVICE_DN,
            "bind_password": "secret",
            "user_search_base": "ou=users,dc=example,dc=org",
            "user_filter": "(uid={username})",
            "start_tls": fail_on == "start_tls",
        }
    )
    with pytest.raises(error):
        ldap._authenticate_sync(cfg, "alice", "alicepassword")
    assert [c.user for c in _FakeConnection.opened] == connections
    assert all(c.unbound for c in _FakeConnection.opened)
