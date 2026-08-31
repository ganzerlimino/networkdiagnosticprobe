"""Aggregate L2 neighbor discovery from LLDP/CDP and MNDP."""

from __future__ import annotations

from dataclasses import replace

from ndp.core.collectors.lldp import collect_lldp_neighbor_state
from ndp.core.collectors.mndp import collect_mndp_neighbor
from ndp.core.state import NeighborState

_WEAK_PORT_NAMES = {"", "bridge", "bridge1", "unknown", "n/a"}


def _is_weak_port(port_id: str | None) -> bool:
    if not port_id:
        return True
    return port_id.strip().lower() in _WEAK_PORT_NAMES


def _merge_neighbor_details(primary: NeighborState, secondary: NeighborState) -> NeighborState:
    if not secondary.available and not any(
        [secondary.port_id, secondary.vlan_id, secondary.switch_name, secondary.chassis_id, secondary.identity]
    ):
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

    mndp_sources = [
        item
        for item in (primary, secondary)
        if item.protocol and item.protocol.upper() == "MNDP"
    ]
    mndp_port = next((item.port_id for item in mndp_sources if item.port_id), None)
    if _is_weak_port(port_id) and mndp_port and not _is_weak_port(mndp_port):
        port_id = mndp_port

    merged = replace(
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
    if merged.message in {"waiting", "no neighbor data", "no mndp neighbor"}:
        merged = replace(merged, message="ok")
    return merged


def _neighbor_has_topology(neighbor: NeighborState) -> bool:
    return neighbor.available or any(
        [
            neighbor.port_id,
            neighbor.vlan_id,
            neighbor.switch_name,
            neighbor.chassis_id,
            neighbor.system_description,
            neighbor.identity,
            neighbor.board,
        ]
    )


def _format_neighbor_failure(lldp: NeighborState, mndp: NeighborState) -> str:
    parts: list[str] = []
    for entry in (lldp, mndp):
        proto = entry.protocol or "neighbor"
        if entry.available:
            continue
        msg = entry.message or "non disponibile"
        parts.append(f"{proto}: {msg}")
    return " · ".join(parts) if parts else "nessun neighbor rilevato"


def _combine_neighbors(lldp: NeighborState, mndp: NeighborState) -> NeighborState:
    lldp_useful = _neighbor_has_topology(lldp)
    mndp_useful = _neighbor_has_topology(mndp)

    if lldp_useful and mndp_useful:
        return _merge_neighbor_details(lldp, mndp)
    if lldp_useful:
        return lldp
    if mndp_useful:
        return mndp

    combined_msg = _format_neighbor_failure(lldp, mndp)
    if lldp.message not in {"waiting", "no neighbor data", "lldpctl unavailable", "lldpd not installed"}:
        return replace(lldp, available=False, message=combined_msg)
    return replace(
        lldp,
        protocol=lldp.protocol or "LLDP",
        available=False,
        message=combined_msg,
    )


def neighbor_from_mndp_device(device: dict[str, object]) -> NeighborState:
    """Build neighbor hints from a connected MNDP device payload."""
    interface = str(device.get("interface") or "").strip() or None
    return NeighborState(
        protocol="MNDP",
        switch_name=str(device["identity"]) if device.get("identity") else None,
        port_id=interface,
        chassis_id=str(device["mac"]) if device.get("mac") else None,
        identity=str(device["identity"]) if device.get("identity") else None,
        software_version=str(device["version"]) if device.get("version") else None,
        platform=str(device["platform"]) if device.get("platform") else None,
        board=str(device["board"]) if device.get("board") else None,
        ipv4_address=str(device["ipv4"]) if device.get("ipv4") else None,
        available=True,
        message="ok (MNDP scan)",
    )


def collect_neighbor_state(
    interface: str,
    *,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
    mndp_listen_seconds: float | None = None,
) -> NeighborState:
    """Return the best available neighbor (LLDP/CDP preferred over MNDP)."""
    return collect_neighbors(
        interface,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
        mndp_listen_seconds=mndp_listen_seconds,
    ).primary


def collect_neighbors(
    interface: str,
    *,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
    mndp_listen_seconds: float | None = None,
) -> "NeighborCollection":
    lldp = collect_lldp_neighbor_state(interface)
    lldp_chassis = lldp.chassis_id if lldp.chassis_id or lldp.system_description else None
    listen_kwargs: dict[str, object] = {
        "gateway_ip": gateway_ip,
        "gateway_mac": gateway_mac,
        "lldp_chassis_mac": lldp_chassis,
    }
    if mndp_listen_seconds is not None:
        listen_kwargs["listen_seconds"] = mndp_listen_seconds
    mndp = collect_mndp_neighbor(interface, **listen_kwargs)

    primary = _combine_neighbors(lldp, mndp)
    entries = [lldp, mndp]
    return NeighborCollection(primary=primary, entries=entries)


class NeighborCollection:
    def __init__(self, *, primary: NeighborState, entries: list[NeighborState]) -> None:
        self.primary = primary
        self.entries = entries
