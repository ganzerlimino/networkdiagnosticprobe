"""Pygame screen rendering helpers."""

from __future__ import annotations

from enum import Enum

from ndp.core.state import ProbeState


class ScreenId(Enum):
    HOME = 0
    SWITCH = 1
    NETWORK = 2
    SYSTEM = 3
    DISCOVER = 4


SCREEN_TITLES = {
    ScreenId.HOME: "Home",
    ScreenId.SWITCH: "Switch",
    ScreenId.NETWORK: "Network",
    ScreenId.SYSTEM: "System",
    ScreenId.DISCOVER: "Discover",
}


def next_screen(current: ScreenId, step: int = 1) -> ScreenId:
    values = list(ScreenId)
    index = (values.index(current) + step) % len(values)
    return values[index]


def _fmt(value: object, fallback: str = "n/a") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def lines_for_screen(screen: ScreenId, state: ProbeState) -> list[str]:
    if screen == ScreenId.HOME:
        ip = "n/a"
        if state.ip.addresses:
            first = state.ip.addresses[0]
            ip = f"{first.address}/{first.prefixlen}"
        link = "UP" if state.link.carrier else "DOWN"
        return [
            f"Link   {link}",
            f"Host   {_fmt(state.system.hostname)}",
            f"IP     {ip}",
            f"MAC    {_fmt(state.link.mac_address)}",
        ]

    if screen == ScreenId.SWITCH:
        if not state.link.carrier:
            return ["Link down", "Collega il cavo"]
        if not state.neighbor.available:
            return [
                "No LLDP/CDP",
                _fmt(state.neighbor.message, "waiting"),
            ]
        return [
            f"Proto  {_fmt(state.neighbor.protocol)}",
            f"Switch {_fmt(state.neighbor.switch_name)}",
            f"Port   {_fmt(state.neighbor.port_id)}",
            f"VLAN   {_fmt(state.neighbor.vlan_id)}",
        ]

    if screen == ScreenId.NETWORK:
        lines = []
        if state.ip.addresses:
            for addr in state.ip.addresses[:2]:
                lines.append(f"{addr.family} {addr.address}/{addr.prefixlen}")
        else:
            lines.append("No IP address")
        lines.append(f"GW  {_fmt(state.ip.gateway)}")
        dns = ", ".join(state.ip.dns_servers[:2]) if state.ip.dns_servers else "n/a"
        lines.append(f"DNS {dns}")
        if state.link.speed_mbps:
            lines.append(f"Link {state.link.speed_mbps} Mbps")
        return lines[:5]

    uptime = _fmt(state.system.uptime_seconds, "n/a")
    if state.system.uptime_seconds is not None:
        uptime = f"{int(state.system.uptime_seconds)} s"
    temp = _fmt(state.system.cpu_temperature_c, "n/a")
    if state.system.cpu_temperature_c is not None:
        temp = f"{state.system.cpu_temperature_c:.1f} C"

    return [
        f"Host  {_fmt(state.system.hostname)}",
        f"Up    {uptime}",
        f"Temp  {temp}",
        f"IF    {state.interface}",
        "NDP ready",
    ]
