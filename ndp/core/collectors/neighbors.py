"""Aggregate L2 neighbor discovery from LLDP/CDP and MNDP."""

from __future__ import annotations

from dataclasses import replace

from ndp.core.collectors.lldp import collect_lldp_neighbor_state
from ndp.core.collectors.mndp import collect_mndp_neighbor
from ndp.core.state import NeighborState


def _merge_neighbor_details(primary: NeighborState, secondary: NeighborState) -> NeighborState:
    if not secondary.available:
        return primary

    lldp_sources = [
        item
        for item in (primary, secondary)
        if item.protocol and item.protocol.upper() in {"LLDP", "CDP"}
    ]
    port_id = next((item.port_id for item in lldp_sources if item.port_id), None)
    vlan_id = next((item.vlan_id for item in lldp_sources if item.vlan_id), None)
    port_id = port_id or primary.port_id or secondary.port_id
    vlan_id = vlan_id or primary.vlan_id or secondary.vlan_id

    return replace(
        primary,
        switch_name=primary.switch_name or secondary.switch_name or secondary.identity,
        port_id=port_id,
        vlan_id=vlan_id,
        chassis_id=primary.chassis_id or secondary.chassis_id,
        system_description=primary.system_description or secondary.system_description,
        identity=primary.identity or secondary.identity,
        software_version=primary.software_version or secondary.software_version,
        platform=primary.platform or secondary.platform,
        board=primary.board or secondary.board,
        ipv4_address=primary.ipv4_address or secondary.ipv4_address,
        med_capabilities=primary.med_capabilities or secondary.med_capabilities,
        med_device_type=primary.med_device_type or secondary.med_device_type,
        poe_allocated_w=primary.poe_allocated_w if primary.poe_allocated_w is not None else secondary.poe_allocated_w,
        poe_requested_w=primary.poe_requested_w if primary.poe_requested_w is not None else secondary.poe_requested_w,
        poe_status=primary.poe_status or secondary.poe_status,
        available=True,
        message=primary.message if primary.available else secondary.message,
    )


def collect_neighbor_state(
    interface: str,
    *,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
) -> NeighborState:
    """Return the best available neighbor (LLDP/CDP preferred over MNDP)."""
    return collect_neighbors(
        interface,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
    ).primary


def collect_neighbors(
    interface: str,
    *,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
) -> "NeighborCollection":
    lldp = collect_lldp_neighbor_state(interface)
    lldp_chassis = lldp.chassis_id if lldp.chassis_id or lldp.system_description else None
    mndp = collect_mndp_neighbor(
        interface,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
        lldp_chassis_mac=lldp_chassis,
    )

    if lldp.port_id or lldp.vlan_id or lldp.switch_name or lldp.available:
        primary = _merge_neighbor_details(lldp, mndp)
    elif mndp.available:
        primary = mndp
    else:
        primary = lldp if lldp.message not in {"waiting", "no neighbor data"} else mndp

    entries = [entry for entry in (lldp, mndp) if entry.available]
    return NeighborCollection(primary=primary, entries=entries)


class NeighborCollection:
    def __init__(self, *, primary: NeighborState, entries: list[NeighborState]) -> None:
        self.primary = primary
        self.entries = entries
