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


def _extract_vlan(
    port_entries: list[dict[str, Any]],
    iface_entry: dict[str, Any] | None = None,
) -> str | None:
    for port in port_entries:
        vlan = port.get("vlan")
        if isinstance(vlan, dict):
            for key in ("id", "pvid", "vlan-id", "vlan_id", "name"):
                vlan_id = _first_value(vlan, key) or (
                    _first_value(vlan.get(key)) if isinstance(vlan.get(key), dict) else None
                )
                if vlan_id:
                    return vlan_id
            vlan_id = _first_value(vlan)
            if vlan_id:
                return vlan_id
        if isinstance(vlan, list):
            for item in vlan:
                if isinstance(item, dict):
                    vlan_id = _first_value(item, "id") or _first_value(item, "pvid") or _first_value(item)
                    if vlan_id:
                        return vlan_id

        ppvid = port.get("ppvid")
        if isinstance(ppvid, dict):
            enabled = ppvid.get("enabled")
            if enabled in {True, "true", "yes", "on", "1"} or _first_value(ppvid, "enabled") in {
                "yes",
                "true",
                "on",
                "1",
            }:
                vlan_id = _first_value(ppvid, "value") or _first_value(ppvid)
                if vlan_id:
                    return vlan_id

    if iface_entry:
        vlan = iface_entry.get("vlan")
        if isinstance(vlan, dict):
            for key in ("vlan-id", "vlan_id", "id", "pvid", "value"):
                vlan_id = _first_value(vlan, key)
                if vlan_id:
                    return vlan_id

    return None


def _normalize_interface_entries(interfaces: object) -> list[dict[str, Any]]:
    if isinstance(interfaces, dict):
        return [interfaces]
    if not isinstance(interfaces, list):
        return []
    return [item for item in interfaces if isinstance(item, dict)]


def _neighbor_score(neighbor: NeighborState) -> tuple[int, int]:
    """Higher is better; tie-break with fresher age."""
    score = 0
    if neighbor.port_id:
        score += 10
    if neighbor.switch_name:
        score += 8
    if neighbor.vlan_id:
        score += 4
    if neighbor.chassis_id:
        score += 2
    if neighbor.system_description:
        descr = neighbor.system_description.lower()
        if any(
            token in descr
            for token in (
                "mikrotik",
                "routeros",
                "crs",
                "css",
                "switch",
                "aruba",
                "instant on",
                "instanton",
                "procurve",
                "hp ",
                "hpe ",
                "cisco",
                "meraki",
                "netgear",
            )
        ):
            score += 6
        if any(token in descr for token in ("linux", "windows", "gentoo", "ubuntu")):
            score -= 4
    age = neighbor.age_seconds if neighbor.age_seconds is not None else 999_999
    return score, -age


def _extract_port_id(port: dict[str, Any]) -> str | None:
    for key in ("id", "descr", "description", "ifname"):
        node = port.get(key)
        if isinstance(node, dict):
            value = _first_value(node)
            if value:
                return value
        elif node is not None and key != "id":
            return str(node)
    local = port.get("local")
    if isinstance(local, dict):
        return _first_value(local, "value") or _first_value(local)
    return None


def _extract_switch_name(chassis: dict[str, Any]) -> str | None:
    name = _first_value(chassis.get("name"))
    if name:
        return name
    descr = _first_value(chassis.get("descr")) or ""
    if not descr:
        return None
    lowered = descr.lower()
    if any(token in lowered for token in ("switch", "aruba", "instant on", "procurve", "mikrotik")):
        return descr[:48]
    first = descr.split(",")[0].strip()
    return first[:48] if first else None


def _parse_interface_entry(iface_entry: dict[str, Any]) -> NeighborState:
    protocol = iface_entry.get("via")
    chassis_entries = iface_entry.get("chassis", [])
    port_entries = iface_entry.get("port", [])

    chassis = chassis_entries[0] if chassis_entries else {}
    port = port_entries[0] if port_entries else {}

    switch_name = _extract_switch_name(chassis)
    chassis_id = _first_value(chassis.get("id"))
    port_id = _extract_port_id(port)
    vlan_id = _extract_vlan(port_entries, iface_entry)
    system_description = _first_value(chassis.get("descr"))
    age_seconds = _parse_age_seconds(iface_entry.get("age"))
    med_device_type, med_capabilities = _extract_med(chassis, port)
    poe_allocated_w, poe_requested_w, poe_status = _extract_poe(port)

    if not any([switch_name, port_id, chassis_id, vlan_id]):
        return NeighborState(
            protocol=protocol,
            available=False,
            message="neighbor present but no usable TLV fields",
            chassis_id=chassis_id,
            system_description=system_description,
            age_seconds=age_seconds,
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


def _pick_best_neighbor(candidates: list[NeighborState]) -> NeighborState | None:
    available = [neighbor for neighbor in candidates if neighbor.available]
    if not available:
        return None
    available.sort(key=_neighbor_score, reverse=True)
    return available[0]


def _consolidate_lldp_candidates(candidates: list[NeighborState]) -> NeighborState:
    if not candidates:
        return NeighborState(available=False, message="no neighbor data")

    best = _pick_best_neighbor([candidate for candidate in candidates if candidate.available])
    if best is None:
        best = next(
            (candidate for candidate in candidates if candidate.switch_name or candidate.chassis_id),
            NeighborState(available=False, message="no neighbor data"),
        )

    for candidate in candidates:
        if candidate.port_id and not best.port_id:
            best.port_id = candidate.port_id
        if candidate.vlan_id and not best.vlan_id:
            best.vlan_id = candidate.vlan_id
        if candidate.switch_name and not best.switch_name:
            best.switch_name = candidate.switch_name
        if candidate.chassis_id and not best.chassis_id:
            best.chassis_id = candidate.chassis_id
        if candidate.system_description and not best.system_description:
            best.system_description = candidate.system_description
        if candidate.protocol and not best.protocol:
            best.protocol = candidate.protocol
        if candidate.age_seconds is not None:
            if best.age_seconds is None:
                best.age_seconds = candidate.age_seconds
            else:
                best.age_seconds = min(best.age_seconds, candidate.age_seconds)

    if best.port_id or best.vlan_id or best.switch_name or best.chassis_id:
        best.available = True
        best.message = "ok"
    return best


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
    matching = [item for item in interfaces if item.get("name") == interface]
    if not matching and interfaces:
        matching = interfaces

    if not matching:
        return NeighborState(available=False, message="no neighbor data")

    candidates = [_parse_interface_entry(item) for item in matching]
    return _consolidate_lldp_candidates(candidates)


def _fetch_lldp_payload(interface: str) -> dict[str, Any] | None:
    commands = (
        ["lldpctl", "-f", "json", interface],
        ["lldpctl", "-f", "json"],
    )
    for command in commands:
        try:
            payload = run_json_command(command)
        except CommandError:
            continue
        except FileNotFoundError:
            return None
        if isinstance(payload, dict) and payload.get("lldp"):
            return payload
    return None


def collect_lldp_neighbor_state(interface: str) -> NeighborState:
    try:
        payload = _fetch_lldp_payload(interface)
    except FileNotFoundError:
        return NeighborState(available=False, message="lldpd not installed")

    if payload is None:
        return NeighborState(available=False, message="lldpctl unavailable")

    return _parse_neighbor_payload(payload, interface)


# Backward-compatible alias
collect_neighbor_state = collect_lldp_neighbor_state
