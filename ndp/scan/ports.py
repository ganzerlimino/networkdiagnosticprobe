"""TCP connect scan and custom port parsing."""

from __future__ import annotations

import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ndp.scan.profiles import PortDefinition, profile_ports

_MAX_CUSTOM_PORTS = 24
_PORT_TOKEN_RE = re.compile(r"^\d{1,5}$")


@dataclass
class PortScanEntry:
    port: int
    service: str
    open: bool
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "port": self.port,
            "service": self.service,
            "open": self.open,
            "latency_ms": self.latency_ms,
        }


@dataclass
class PortScanResult:
    host: str
    profile: str
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entries: list[PortScanEntry] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def open_ports(self) -> list[PortScanEntry]:
        return [entry for entry in self.entries if entry.open]

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "profile": self.profile,
            "scanned_at": self.scanned_at.isoformat(),
            "duration_ms": round(self.duration_ms, 1),
            "open_count": len(self.open_ports),
            "scanned_count": len(self.entries),
            "entries": [entry.to_dict() for entry in self.entries],
            "open_ports": [entry.to_dict() for entry in self.open_ports],
        }


def parse_custom_ports(raw: str | list[int] | None) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, list):
        ports = [int(port) for port in raw if 1 <= int(port) <= 65535]
        return sorted(set(ports))[:_MAX_CUSTOM_PORTS]

    ports: list[int] = []
    for token in re.split(r"[\s,;]+", str(raw).strip()):
        if not token:
            continue
        if not _PORT_TOKEN_RE.match(token):
            raise ValueError(f"porta non valida: {token}")
        port = int(token)
        if port < 1 or port > 65535:
            raise ValueError(f"porta fuori range: {port}")
        ports.append(port)
    return sorted(set(ports))[:_MAX_CUSTOM_PORTS]


def probe_tcp_port(host: str, port: int, timeout_seconds: float) -> tuple[bool, float | None]:
    started = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    try:
        result = sock.connect_ex((host, port))
        if result != 0:
            return False, None
        latency_ms = (time.monotonic() - started) * 1000.0
        return True, latency_ms
    except OSError:
        return False, None
    finally:
        sock.close()


def scan_ports(
    host: str,
    profile: str,
    *,
    custom_ports: list[int] | None = None,
    timeout_seconds: float = 1.5,
    max_workers: int = 12,
) -> PortScanResult:
    host = host.strip()
    if not host:
        raise ValueError("host richiesto")

    definitions = profile_ports(profile, custom_ports)
    if not definitions:
        raise ValueError("nessuna porta da scansionare")

    started = time.monotonic()
    entries: list[PortScanEntry] = []
    workers = min(max_workers, max(1, len(definitions)))

    def _scan(defn: PortDefinition) -> PortScanEntry:
        is_open, latency = probe_tcp_port(host, defn.port, timeout_seconds)
        return PortScanEntry(
            port=defn.port,
            service=defn.service,
            open=is_open,
            latency_ms=latency,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_scan, defn) for defn in definitions]
        for future in as_completed(futures):
            entries.append(future.result())

    entries.sort(key=lambda item: item.port)
    return PortScanResult(
        host=host,
        profile=profile,
        entries=entries,
        duration_ms=(time.monotonic() - started) * 1000.0,
    )
