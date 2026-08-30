"""FastAPI request/response models (module-level for Pydantic forward-ref resolution)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigPayload(BaseModel):
    yaml: str


class AdhocPayload(BaseModel):
    host: str


class ConfigValuesPayload(BaseModel):
    values: dict[str, object]


class ServiceRestartPayload(BaseModel):
    services: list[str] = Field(default_factory=lambda: ["ndp"])


class ShutdownPayload(BaseModel):
    confirm: bool = False


class PingRunPayload(BaseModel):
    hosts: list[str] | None = None


class LivePingPayload(BaseModel):
    hosts: list[str] = Field(..., min_length=1, max_length=3)
    interval: float = Field(default=1.0, ge=0.2, le=10.0)
    max_samples: int = Field(default=60, ge=1, le=300)


class PortScanPayload(BaseModel):
    host: str
    profile: str = Field(..., pattern="^(standard|industrial|custom)$")
    ports: str | list[int] | None = None
    timeout_ms: int = Field(default=1500, ge=300, le=5000)


class DnsLookupPayload(BaseModel):
    hostname: str


class NetworkCheckPayload(BaseModel):
    hostnames: list[str] = Field(default_factory=list)
    include_gateway: bool = True


class MtuDiscoverPayload(BaseModel):
    host: str
    start_mtu: int = Field(default=1500, ge=576, le=9000)
    min_mtu: int = Field(default=576, ge=576, le=9000)
