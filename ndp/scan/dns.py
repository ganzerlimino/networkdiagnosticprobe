"""DNS resolution and gateway reachability checks."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ndp.core.collectors.ping import ping_host
from ndp.scan.ports import PortScanEntry, probe_tcp_port
from ndp.scan.profiles import GATEWAY_QUICK_PORTS, PortDefinition


@dataclass
class DnsLookupResult:
    hostname: str
    addresses: list[str] = field(default_factory=list)
    error: str | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "hostname": self.hostname,
            "addresses": self.addresses,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "ok": bool(self.addresses),
        }


@dataclass
class DnsServerCheck:
    server: str
    reachable_tcp_53: bool = False
    resolves: bool = False
    answers: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "server": self.server,
            "reachable_tcp_53": self.reachable_tcp_53,
            "resolves": self.resolves,
            "answers": self.answers,
            "message": self.message,
            "ok": self.resolves or self.reachable_tcp_53,
        }


@dataclass
class GatewayCheckResult:
    gateway: str
    ping_reachable: bool = False
    ping_rtt_ms: float | None = None
    ping_message: str = ""
    open_ports: list[PortScanEntry] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "gateway": self.gateway,
            "ping_reachable": self.ping_reachable,
            "ping_rtt_ms": self.ping_rtt_ms,
            "ping_message": self.ping_message,
            "open_ports": [entry.to_dict() for entry in self.open_ports],
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class NetworkDiagnosticsResult:
    lookups: list[DnsLookupResult] = field(default_factory=list)
    dns_servers: list[DnsServerCheck] = field(default_factory=list)
    gateway: GatewayCheckResult | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "lookups": [item.to_dict() for item in self.lookups],
            "dns_servers": [item.to_dict() for item in self.dns_servers],
            "gateway": self.gateway.to_dict() if self.gateway else None,
            "checked_at": self.checked_at.isoformat(),
        }


def resolve_hostname(hostname: str) -> DnsLookupResult:
    name = hostname.strip()
    if not name:
        return DnsLookupResult(hostname="", error="hostname vuoto")

    started = time.monotonic()
    try:
        infos = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return DnsLookupResult(hostname=name, error=str(exc))

    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0] not in addresses:
            addresses.append(sockaddr[0])

    latency_ms = (time.monotonic() - started) * 1000.0
    return DnsLookupResult(hostname=name, addresses=addresses, latency_ms=latency_ms)


def _dig_query(server: str, query: str) -> tuple[bool, list[str], str]:
    if not shutil.which("dig"):
        return False, [], "dig non disponibile"

    try:
        completed = subprocess.run(
            ["dig", f"@{server}", "+time=2", "+tries=1", "+short", query],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, [], str(exc)

    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode == 0 and lines:
        return True, lines, "ok"
    detail = completed.stderr.strip() or completed.stdout.strip() or "nessuna risposta"
    return False, lines, detail[:120]


def check_dns_server(server: str, query: str = "example.com") -> DnsServerCheck:
    tcp_open, _ = probe_tcp_port(server, 53, timeout_seconds=1.5)
    resolves, answers, message = _dig_query(server, query)
    if not resolves and tcp_open and not shutil.which("dig"):
        message = "porta 53/tcp aperta (dig assente per query)"
    return DnsServerCheck(
        server=server,
        reachable_tcp_53=tcp_open,
        resolves=resolves,
        answers=answers,
        message=message,
    )


def check_gateway(gateway: str, *, timeout_seconds: float = 1.5) -> GatewayCheckResult:
    ping = ping_host(gateway, count=1, timeout_seconds=2.0)
    open_ports: list[PortScanEntry] = []
    for defn in GATEWAY_QUICK_PORTS:
        is_open, latency = probe_tcp_port(gateway, defn.port, timeout_seconds)
        if is_open:
            open_ports.append(
                PortScanEntry(
                    port=defn.port,
                    service=defn.service,
                    open=True,
                    latency_ms=latency,
                )
            )
    return GatewayCheckResult(
        gateway=gateway,
        ping_reachable=ping.reachable,
        ping_rtt_ms=ping.rtt_ms,
        ping_message=ping.message,
        open_ports=open_ports,
    )


def run_network_diagnostics(
    *,
    hostnames: list[str],
    dns_servers: list[str],
    gateway: str | None,
) -> NetworkDiagnosticsResult:
    lookups = [resolve_hostname(name) for name in hostnames if name.strip()]
    server_checks = [check_dns_server(server) for server in dns_servers if server.strip()]
    gateway_result = check_gateway(gateway) if gateway else None
    return NetworkDiagnosticsResult(
        lookups=lookups,
        dns_servers=server_checks,
        gateway=gateway_result,
    )
