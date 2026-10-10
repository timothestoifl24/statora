import asyncio
from types import SimpleNamespace

import dns.resolver
import httpx
import pytest
import respx

from statora.checks import CheckTarget, run_check
from statora.checks import dns as dns_check
from statora.db.models import MonitorStatus, MonitorType
from statora.schemas.monitor import HttpConfig, parse_config


def target(type_: MonitorType, target: str, **config) -> CheckTarget:
    return CheckTarget(
        id=1, type=type_, target=target, timeout_s=2, config=parse_config(type_, config).model_dump()
    )


def test_status_ranges():
    cfg = HttpConfig(expected_status=["200-299", "301"])
    assert cfg.status_ok(204) and cfg.status_ok(301)
    assert not cfg.status_ok(302) and not cfg.status_ok(500)
    with pytest.raises(ValueError):
        HttpConfig(expected_status=["2xx"])


@respx.mock
async def test_http_up():
    respx.get("https://svc.test/").respond(200, text="hello world")
    result = await run_check(target(MonitorType.HTTP, "https://svc.test/", keyword="hello"))
    assert result.status == MonitorStatus.UP
    assert result.latency_ms is not None


@respx.mock
async def test_http_unexpected_status():
    respx.get("https://svc.test/").respond(503)
    result = await run_check(target(MonitorType.HTTP, "https://svc.test/"))
    assert result.status == MonitorStatus.DOWN
    assert "503" in result.message


@respx.mock
async def test_http_keyword_missing_and_inverted():
    respx.get("https://svc.test/").respond(200, text="maintenance mode")
    missing = await run_check(target(MonitorType.HTTP, "https://svc.test/", keyword="welcome"))
    assert missing.status == MonitorStatus.DOWN
    inverted = await run_check(
        target(MonitorType.HTTP, "https://svc.test/", keyword="maintenance", invert_keyword=True)
    )
    assert inverted.status == MonitorStatus.DOWN


@respx.mock
async def test_http_timeout_and_connection_error():
    respx.get("https://slow.test/").mock(side_effect=httpx.ReadTimeout("timed out"))
    respx.get("https://gone.test/").mock(side_effect=httpx.ConnectError("refused"))
    assert (await run_check(target(MonitorType.HTTP, "https://slow.test/"))).message.startswith("Timeout")
    assert (await run_check(target(MonitorType.HTTP, "https://gone.test/"))).status == MonitorStatus.DOWN


@respx.mock
async def test_http_degraded_threshold(monkeypatch):
    respx.get("https://svc.test/").respond(200)
    times = iter([0.0, 2.0])  # 2000 ms response time
    monkeypatch.setattr("statora.checks.http.time", SimpleNamespace(perf_counter=lambda: next(times)))
    result = await run_check(target(MonitorType.HTTP, "https://svc.test/", degraded_threshold_ms=500))
    assert result.status == MonitorStatus.DEGRADED


async def test_tcp_open_and_closed():
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        up = await run_check(target(MonitorType.TCP, "127.0.0.1", port=port))
    assert up.status == MonitorStatus.UP
    down = await run_check(target(MonitorType.TCP, "127.0.0.1", port=port))
    assert down.status == MonitorStatus.DOWN


class _FakeRdata:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return self._text


async def test_dns_expected_value(monkeypatch):
    async def fake_resolve(self, name, rdtype, lifetime):
        if name == "missing.test":
            raise dns.resolver.NXDOMAIN
        return [_FakeRdata("93.184.215.14")]

    monkeypatch.setattr(dns_check.dns.asyncresolver.Resolver, "resolve", fake_resolve)
    ok = await run_check(target(MonitorType.DNS, "example.test", expected_value="93.184.215.14"))
    assert ok.status == MonitorStatus.UP
    wrong = await run_check(target(MonitorType.DNS, "example.test", expected_value="10.0.0.1"))
    assert wrong.status == MonitorStatus.DOWN
    nx = await run_check(target(MonitorType.DNS, "missing.test"))
    assert "NXDOMAIN" in nx.message


async def test_broken_check_never_raises(monkeypatch):
    async def boom(_):
        raise RuntimeError("bug")

    monkeypatch.setitem(__import__("statora.checks", fromlist=["CHECKS"]).CHECKS, MonitorType.PING, boom)
    result = await run_check(target(MonitorType.PING, "127.0.0.1"))
    assert result.status == MonitorStatus.DOWN and "bug" in result.message
