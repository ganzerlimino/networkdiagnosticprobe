"""Aggregate L2 neighbor discovery from LLDP/CDP and MNDP."""

from __future__ import annotations

from ndp.core.collectors.lldp import collect_lldp_neighbor_state
from ndp.core.collectors.mndp import collect_mndp_neighbor
from ndp.core.state import NeighborState

_PROTOCOL_PRIORITY = {
    "LLDP": 0,
    "CDP": 1,
    "MNDP": 2,
}


def _priority(neighbor: NeighborState) -> int:
    protocol = (neighbor.protocol or "").upper()
    return _PROTOCOL_PRIORITY.get(protocol, 99)


def _pick_primary(neighbors: list[NeighborState]) -> NeighborState:
    available = [neighbor for neighbor in neighbors if neighbor.available]
    if not available:
        return NeighborState(available=False, message="no neighbor")
    available.sort(key=_priority)
    return available[0]


def collect_neighbor_state(interface: str) -> NeighborState:
    """Return the best available neighbor (LLDP/CDP preferred over MNDP)."""
    return collect_neighbors(interface).primary


def collect_neighbors(interface: str) -> "NeighborCollection":
    lldp = collect_lldp_neighbor_state(interface)
    mndp = collect_mndp_neighbor(interface)
    entries = [lldp, mndp]
    primary = _pick_primary(entries)
    return NeighborCollection(primary=primary, entries=entries)


class NeighborCollection:
    def __init__(self, *, primary: NeighborState, entries: list[NeighborState]) -> None:
        self.primary = primary
        self.entries = entries
