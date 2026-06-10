"""Shared probe state model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class LinkState:
    operstate: str = "unknown"
    carrier: bool = False
    speed_mbps: int | None = None
    duplex: str | None = None
    mac_address: str | None = None


@dataclass
class IpAddress:
    family: str
    address: str
    prefixlen: int


@dataclass
class IpState:
    addresses: list[IpAddress] = field(default_factory=list)
    gateway: str | None = None
    dns_servers: list[str] = field(default_factory=list)
    dhcp: bool | None = None


@dataclass
class NeighborState:
    protocol: str | None = None
    switch_name: str | None = None
    port_id: str | None = None
    chassis_id: str | None = None
    vlan_id: str | None = None
    system_description: str | None = None
    age_seconds: int | None = None
    last_seen: datetime | None = None
    available: bool = False
    message: str = "waiting"


@dataclass
class SystemState:
    hostname: str | None = None
    uptime_seconds: float | None = None
    cpu_temperature_c: float | None = None


@dataclass
class ProbeState:
    interface: str
    updated_at: datetime = field(default_factory=_utc_now)
    link: LinkState = field(default_factory=LinkState)
    ip: IpState = field(default_factory=IpState)
    neighbor: NeighborState = field(default_factory=NeighborState)
    system: SystemState = field(default_factory=SystemState)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def touch(self) -> None:
        self.updated_at = _utc_now()
