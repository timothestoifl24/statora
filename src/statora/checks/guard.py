"""Addresses monitors may not reach (STATORA_MONITOR_BLOCKED_NETWORKS).

Checks connect from the server, so a monitor pointed at the cloud metadata service could read the
instance's credentials through its results. The host is resolved and checked right before each
check, and again for every HTTP redirect. A name that resolves differently between this check and
the connection (DNS rebinding) is not caught; the blocklist is a guard rail, not a sandbox.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from statora.config import get_settings
from statora.db.models import MonitorType
from statora.schemas.monitor import DnsConfig

from .base import CheckTarget


def host_of(target: CheckTarget) -> str | None:
    """The host a check connects to, or None when it connects to nothing it is told to."""
    kind = MonitorType(target.type)
    if kind == MonitorType.HTTP:
        return urlsplit(target.target).hostname
    if kind == MonitorType.DNS:
        return DnsConfig.model_validate(target.config).resolver  # the target is only a name to look up
    if kind == MonitorType.GROUP:
        return None
    return target.target.strip() or None


async def blocked_address(host: str | None) -> str | None:
    """The first address of `host` in a blocked network, or None when it may be reached."""
    networks = get_settings().blocked_networks
    if not host or not networks:
        return None
    host = host.strip("[]")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            return None  # unresolvable: the check itself reports it
        addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    for address in addresses:
        mapped = getattr(address, "ipv4_mapped", None)
        if any((mapped or address) in network for network in networks):
            return str(address)
    return None


def blocked_message(host: str, address: str) -> str:
    shown = host if host == address else f"{host} ({address})"
    return f"Target {shown} is in a blocked network (STATORA_MONITOR_BLOCKED_NETWORKS)"
