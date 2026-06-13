"""Discovery data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_mac(mac: str) -> str:
    cleaned = mac.strip().lower().replace("-", ":")
    parts = cleaned.split(":")
    if len(parts) == 6 and all(len(part) <= 2 for part in parts):
        return ":".join(part.zfill(2) for part in parts)
    return cleaned


@dataclass(frozen=True)
class DiscoveredHost:
    ip: str
    mac: str
    vendor: str | None = None
    hostname: str | None = None
    source: str = "arp"

    def __post_init__(self) -> None:
        object.__setattr__(self, "mac", normalize_mac(self.mac))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanSnapshot:
    interface: str
    hosts: list[DiscoveredHost] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=_utc_now)
    source: str = "arp-scan"

    @property
    def host_count(self) -> int:
        return len(self.hosts)

    def macs(self) -> set[str]:
        return {host.mac for host in self.hosts}

    def by_mac(self) -> dict[str, DiscoveredHost]:
        return {host.mac: host for host in self.hosts}

    def to_dict(self) -> dict[str, Any]:
        return {
            "interface": self.interface,
            "scanned_at": self.scanned_at.isoformat(),
            "source": self.source,
            "host_count": self.host_count,
            "hosts": [host.to_dict() for host in self.hosts],
        }
