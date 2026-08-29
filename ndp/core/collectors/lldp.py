"""LLDP/CDP neighbor collector via lldpctl."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ndp.core.state import NeighborState
from ndp.core.subprocess_runner import CommandError, run_json_command


def _first_value(node: dict[str, Any] | None, key: str = "value") -> str | None:
    if not node:
        return None
    if isinstance(node, dict):
        if key in node:
            value = node[key]
            if isinstance(value, dict):
                return _first_value(value)
            if value is not None:
                return str(value)
        for nested_key in ("value", "id"):
            if nested_key in node:
                nested = node[nested_key]
                if isinstance(nested, dict):
                    resolved = _first_value(nested)
                    if resolved is not None:
                        return resolved
                elif nested is not None:
                    return str(nested)
    return None


def _parse_age_seconds(age: str | None) -> int | None:
    if not age:
        return None
    match = re.match(r"^(?:(\d+):)?(\d+):(\d+)$", age)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def _extract_vlan(port_entries: list[dict[str, Any]]) -> str | None:
    for port in port_entries:
        vlan = port.get("vlan")
        if isinstance(vlan, dict):
            vlan_id = _first_value(vlan, "id") or _first_value(vlan)
            if vlan_id:
                return vlan_id
        if isinstance(vlan, list):
            for item in vlan:
                if isinstance(item, dict):
                    vlan_id = _first_value(item, "id") or _first_value(item)
                    if vlan_id:
                        return vlan_id
    return None


def _normalize_interface_entries(interfaces: object) -> list[dict[str, Any]]:
    if isinstance(interfaces, dict):
        return [interfaces]
    if not isinstance(interfaces, list):
        return []
    return [item for item in interfaces if isinstance(item, dict)]


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _extract_med(chassis: dict[str, Any], port: dict[str, Any]) -> tuple[str | None, str | None]:
    med_device_type: str | None = None
    med_capabilities: str | None = None

    for node in (chassis.get("med"), port.get("med")):
        if not isinstance(node, dict):
            continue
        device = node.get("device")
        if isinstance(device, dict):
            med_device_type = med_device_type or _first_value(device.get("type")) or _first_value(device)
        capabilities = node.get("capability")
        if isinstance(capabilities, list):
            names = []
            for item in capabilities:
                if isinstance(item, dict):
                    name = _first_value(item.get("type")) or _first_value(item)
                    if name:
                        names.append(name)
            if names:
                med_capabilities = ", ".join(names)
        elif isinstance(capabilities, dict):
            med_capabilities = med_capabilities or _first_value(capabilities.get("type")) or _first_value(
                capabilities
            )

    return med_device_type, med_capabilities


def _extract_poe(port: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    power = port.get("power")
    if not isinstance(power, dict):
        return None, None, None

    allocated = _parse_float(_first_value(power.get("allocated")))
    requested = _parse_float(_first_value(power.get("requested")))
    status = _first_value(power.get("status")) or _first_value(power.get("supported"))
    return allocated, requested, status


def _parse_neighbor_payload(payload: dict[str, Any], interface: str) -> NeighborState:
    lldp_root = payload.get("lldp", {})
    interfaces = _normalize_interface_entries(lldp_root.get("interface", []))
    iface_entry = next((item for item in interfaces if item.get("name") == interface), None)
    if not iface_entry and interfaces:
        iface_entry = interfaces[0]

    if not iface_entry:
        return NeighborState(available=False, message="no neighbor data")

    protocol = iface_entry.get("via")
    chassis_entries = iface_entry.get("chassis", [])
    port_entries = iface_entry.get("port", [])

    chassis = chassis_entries[0] if chassis_entries else {}
    port = port_entries[0] if port_entries else {}

    switch_name = _first_value(chassis.get("name"))
    chassis_id = _first_value(chassis.get("id"))
    port_id = _first_value(port.get("id")) or _first_value(port.get("descr"))
    vlan_id = _extract_vlan(port_entries)
    system_description = _first_value(chassis.get("descr"))
    age_seconds = _parse_age_seconds(iface_entry.get("age"))
    med_device_type, med_capabilities = _extract_med(chassis, port)
    poe_allocated_w, poe_requested_w, poe_status = _extract_poe(port)

    if not any([switch_name, port_id, chassis_id, vlan_id]):
        return NeighborState(
            protocol=protocol,
            available=False,
            message="neighbor present but no usable TLV fields",
        )

    return NeighborState(
        protocol=protocol,
        switch_name=switch_name,
        port_id=port_id,
        chassis_id=chassis_id,
        vlan_id=vlan_id,
        system_description=system_description,
        age_seconds=age_seconds,
        med_device_type=med_device_type,
        med_capabilities=med_capabilities,
        poe_allocated_w=poe_allocated_w,
        poe_requested_w=poe_requested_w,
        poe_status=poe_status,
        last_seen=datetime.now(timezone.utc),
        available=True,
        message="ok",
    )


def collect_lldp_neighbor_state(interface: str) -> NeighborState:
    try:
        payload = run_json_command(["lldpctl", "-f", "json", interface])
    except CommandError:
        return NeighborState(available=False, message="lldpctl unavailable")
    except FileNotFoundError:
        return NeighborState(available=False, message="lldpd not installed")

    if not isinstance(payload, dict):
        return NeighborState(available=False, message="invalid lldpctl response")

    return _parse_neighbor_payload(payload, interface)


# Backward-compatible alias
collect_neighbor_state = collect_lldp_neighbor_state
