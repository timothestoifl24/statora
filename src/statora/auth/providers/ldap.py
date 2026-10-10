"""LDAP login (search + bind or direct bind). ldap3 is blocking, so calls run in a thread."""

import asyncio
import ssl

from ldap3 import ALL_ATTRIBUTES, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import escape_rdn

from statora.db.models import AuthProvider
from statora.schemas.auth_provider import LdapConfig

from .base import AuthError, ExternalIdentity, load_config


def _server(cfg: LdapConfig) -> Server:
    tls = Tls(validate=ssl.CERT_REQUIRED if cfg.verify_tls else ssl.CERT_NONE)
    return Server(cfg.server_uri, use_ssl=cfg.server_uri.startswith("ldaps://"), tls=tls, connect_timeout=10)


def _connect(cfg: LdapConfig, user: str | None, password: str | None) -> Connection:
    conn = Connection(_server(cfg), user=user, password=password, receive_timeout=10, raise_exceptions=False)
    conn.open()
    if cfg.start_tls:
        conn.start_tls()
    if not conn.bind():
        conn.unbind()
        raise AuthError("Invalid username or password")
    return conn


def _first(entry, attr: str) -> str | None:
    if not attr or attr not in entry.entry_attributes:
        return None
    value = entry[attr].value
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value is not None else None


def _authenticate_sync(cfg: LdapConfig, username: str, password: str) -> ExternalIdentity:
    if not password:
        # An empty password would be an "unauthenticated bind", which many servers accept.
        raise AuthError("Invalid username or password")

    if cfg.bind_dn_template:
        user_dn = cfg.bind_dn_template.format(username=escape_rdn(username))
        conn = _connect(cfg, user_dn, password)
        conn.search(user_dn, "(objectClass=*)", search_scope="BASE", attributes=ALL_ATTRIBUTES)
    else:
        service = _connect(cfg, cfg.bind_dn, cfg.bind_password)
        search_filter = cfg.user_filter.format(username=escape_filter_chars(username))
        service.search(cfg.user_search_base, search_filter, SUBTREE, attributes=ALL_ATTRIBUTES, size_limit=2)
        entries = list(service.entries)
        service.unbind()
        if len(entries) != 1:
            raise AuthError("Invalid username or password")
        user_dn = entries[0].entry_dn
        conn = _connect(cfg, user_dn, password)
        conn.search(user_dn, "(objectClass=*)", search_scope="BASE", attributes=ALL_ATTRIBUTES)

    try:
        if not conn.entries:
            raise AuthError("User entry not readable after bind")
        entry = conn.entries[0]
        groups: list[str] = []
        if cfg.group_search_base:
            conn.search(
                cfg.group_search_base,
                cfg.group_filter.format(
                    user_dn=escape_filter_chars(user_dn), username=escape_filter_chars(username)
                ),
                SUBTREE,
                attributes=[cfg.group_name_attr],
            )
            groups = [str(g[cfg.group_name_attr].value) for g in conn.entries if cfg.group_name_attr in g]
        elif "memberOf" in entry.entry_attributes:
            groups = [str(dn) for dn in entry["memberOf"].values]
        return ExternalIdentity(
            external_id=user_dn,
            username=_first(entry, cfg.username_attr) or username,
            email=_first(entry, cfg.email_attr),
            display_name=_first(entry, cfg.name_attr),
            groups=groups,
        )
    finally:
        conn.unbind()


async def authenticate(provider: AuthProvider, username: str, password: str) -> ExternalIdentity:
    cfg: LdapConfig = load_config(provider)
    try:
        return await asyncio.to_thread(_authenticate_sync, cfg, username.strip(), password)
    except LDAPException as exc:
        raise AuthError(f"LDAP server error: {exc}") from exc


def _test_sync(cfg: LdapConfig) -> str:
    if cfg.bind_dn:
        conn = _connect(cfg, cfg.bind_dn, cfg.bind_password)
        conn.unbind()
        return f"Connected and bound as {cfg.bind_dn}"
    conn = Connection(_server(cfg), receive_timeout=10)
    conn.open()
    conn.unbind()
    return "Connected (no service account configured)"


async def test_connection(provider: AuthProvider) -> str:
    try:
        return await asyncio.to_thread(_test_sync, load_config(provider))
    except AuthError as exc:
        raise AuthError("Service account bind failed") from exc
    except LDAPException as exc:
        raise AuthError(f"LDAP error: {exc}") from exc
