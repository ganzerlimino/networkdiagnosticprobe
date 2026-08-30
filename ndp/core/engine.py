"""Probe polling engine and neighbor cache."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Any

from ndp.core.collectors import (
    collect_ip_state,
    collect_link_state,
    collect_neighbors,
    collect_system_state,
)
from ndp.core.collectors.neighbors import _merge_neighbor_details, neighbor_from_mndp_device
from ndp.core.config import NdpConfig
from ndp.core.state import NeighborState, ProbeState
from ndp.discovery.neigh import lookup_neighbor_mac

logger = logging.getLogger(__name__)

_QUICK_MNDP_LISTEN_SECONDS = 1.0


class ProbeEngine:
    def __init__(self, config: NdpConfig) -> None:
        self.config = config
        self.state = ProbeState(interface=config.interface)
        self._cached_neighbor: NeighborState | None = None
        self._cached_neighbor_at: float = 0.0

    def refresh(self) -> ProbeState:
        interface = self.config.interface

        self.state.link = collect_link_state(interface)
        self.state.ip = collect_ip_state(interface)
        self.state.system = collect_system_state()
        self.state.neighbor, self.state.neighbors = self._resolve_neighbors(interface)
        self.state.touch()

        return self.state

    def apply_mndp_device(self, device: dict[str, Any] | None) -> NeighborState:
        """Merge connected MNDP device hints into the current neighbor snapshot."""
        if not device:
            return self.state.neighbor
        hints = neighbor_from_mndp_device(device)
        merged = _merge_neighbor_details(self.state.neighbor, hints)
        self.state.neighbor = merged
        self._cached_neighbor = merged
        self._cached_neighbor_at = time.monotonic()
        return merged

    def _mndp_listen_seconds(self) -> float:
        full_listen = self.config.discovery_mndp_listen_seconds
        if full_listen <= 0:
            return _QUICK_MNDP_LISTEN_SECONDS

        cached = self._cached_neighbor
        if cached is None:
            return full_listen

        missing_topology = not cached.port_id and not cached.vlan_id
        cache_fresh = (time.monotonic() - self._cached_neighbor_at) <= self.config.lldp_cache_ttl_seconds
        if missing_topology or not cache_fresh:
            return full_listen
        return min(full_listen, _QUICK_MNDP_LISTEN_SECONDS)

    def _resolve_neighbors(self, interface: str) -> tuple[NeighborState, list[NeighborState]]:
        if not self.state.link.carrier:
            empty = NeighborState(available=False, message="link down")
            return empty, []

        collection = collect_neighbors(
            interface,
            gateway_ip=self.state.ip.gateway,
            gateway_mac=lookup_neighbor_mac(interface, self.state.ip.gateway or ""),
            mndp_listen_seconds=self._mndp_listen_seconds(),
        )
        now = time.monotonic()
        primary = collection.primary

        if primary.available:
            self._cached_neighbor = primary
            self._cached_neighbor_at = now
            return primary, collection.entries

        if (
            self._cached_neighbor
            and (now - self._cached_neighbor_at) <= self.config.lldp_cache_ttl_seconds
        ):
            age = int(now - self._cached_neighbor_at)
            cached = replace(
                self._cached_neighbor,
                message=f"cached ({age}s ago)",
            )
            return cached, collection.entries

        return primary, collection.entries

    def poll_interval(self) -> float:
        if self.state.link.carrier:
            return self.config.poll_interval_link_up
        return self.config.poll_interval_link_down
