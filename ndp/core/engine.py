"""Probe polling engine and neighbor cache."""

from __future__ import annotations

import logging
import time
from dataclasses import replace

from ndp.core.collectors import (
    collect_ip_state,
    collect_link_state,
    collect_neighbors,
    collect_system_state,
)
from ndp.core.config import NdpConfig
from ndp.core.state import NeighborState, ProbeState

logger = logging.getLogger(__name__)


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

    def _resolve_neighbors(self, interface: str) -> tuple[NeighborState, list[NeighborState]]:
        if not self.state.link.carrier:
            empty = NeighborState(available=False, message="link down")
            return empty, []

        collection = collect_neighbors(interface)
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
