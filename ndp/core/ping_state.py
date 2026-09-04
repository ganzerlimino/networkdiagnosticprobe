"""Ping result models shared across core, UI, and CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PingResult:
    host: str
    reachable: bool
    packets_sent: int
    packets_received: int
    packet_loss_pct: float
    rtt_ms: float | None
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "reachable": self.reachable,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "packet_loss_pct": self.packet_loss_pct,
            "rtt_ms": self.rtt_ms,
            "message": self.message,
        }


@dataclass(frozen=True)
class PingTarget:
    label: str
    host: str
    kind: str  # builtin | custom | adhoc


@dataclass
class PingTargetResult:
    label: str
    host: str
    kind: str
    result: PingResult

    def to_dict(self) -> dict[str, object]:
        data = self.result.to_dict()
        data["label"] = self.label
        data["kind"] = self.kind
        return data


@dataclass
class PingSuiteState:
    results: list[PingTargetResult] = field(default_factory=list)
    adhoc_host: str | None = None
    running: bool = False
    last_run_at: datetime | None = None
    message: str = "○ per eseguire ping"

    def to_dict(self) -> dict[str, object]:
        return {
            "running": self.running,
            "adhoc_host": self.adhoc_host,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "message": self.message,
            "results": [item.to_dict() for item in self.results],
        }
