"""IP configuration collector via iproute2 JSON output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ndp.core.state import IpAddress, IpState
from ndp.core.subprocess_runner import CommandError, run_json_command


def _first_value(node: dict[str, Any] | None, key: str = "value") -> str | None:
    if not node:
        return None
    if isinstance(node, dict):
        value = node.get(key)
        if value is not None:
            return str(value)
    return None


def _parse_addresses(iface_data: list[dict[str, Any]]) -> list[IpAddress]:
    addresses: list[IpAddress] = []
    if not iface_data:
        return addresses

    for addr_info in iface_data[0].get("addr_info", []):
        if addr_info.get("scope") == "link":
            continue
        local = addr_info.get("local")
        family = addr_info.get("family")
        prefixlen = addr_info.get("prefixlen")
        if local and family and prefixlen is not None:
            addresses.append(
                IpAddress(family=str(family), address=str(local), prefixlen=int(prefixlen))
            )
    return addresses


def _parse_gateway(route_data: list[dict[str, Any]]) -> str | None:
    for route in route_data:
        if route.get("dst") == "default" and route.get("gateway"):
            return str(route["gateway"])
    return None


def _read_resolv_conf_dns() -> list[str]:
    path = Path("/etc/resolv.conf")
    servers: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("nameserver "):
                servers.append(line.split()[1])
    except OSError:
        return []
    return servers


def _read_resolvectl_dns(interface: str) -> list[str]:
    try:
        data = run_json_command(["resolvectl", "dns", interface])
    except (CommandError, FileNotFoundError):
        return []

    if isinstance(data, list):
        return [str(item) for item in data if item]
    return []


def collect_ip_state(interface: str) -> IpState:
    addresses: list[IpAddress] = []
    gateway = None

    try:
        iface_data = run_json_command(["ip", "-j", "addr", "show", "dev", interface])
        addresses = _parse_addresses(iface_data)
    except (CommandError, FileNotFoundError):
        pass

    try:
        route_data = run_json_command(["ip", "-j", "route", "show", "dev", interface])
        gateway = _parse_gateway(route_data)
    except (CommandError, FileNotFoundError):
        pass

    dns_servers = _read_resolvectl_dns(interface) or _read_resolv_conf_dns()

    dhcp = None
    if addresses:
        dhcp = any(addr.family == "inet" for addr in addresses)

    return IpState(
        addresses=addresses,
        gateway=gateway,
        dns_servers=dns_servers,
        dhcp=dhcp,
    )
