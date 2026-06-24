"""Pygame screen rendering helpers."""

from __future__ import annotations

from enum import Enum

from ndp.core.state import ProbeState


class ScreenId(Enum):
    HOME = 0
    SWITCH = 1
    NETWORK = 2
    PING = 3
    SYSTEM = 4
    DISCOVER = 5


SCREEN_TITLES = {
    ScreenId.HOME: "Home",
    ScreenId.SWITCH: "Switch",
    ScreenId.NETWORK: "Network",
    ScreenId.PING: "Ping",
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


def _ping_line(label: str, host: str, reachable: bool, rtt_ms: float | None, message: str) -> str:
    short_label = label[:6]
    short_host = host[:12]
    if reachable and rtt_ms is not None:
        return f"{short_label} {short_host} {rtt_ms:.0f}ms"
    return f"{short_label} {short_host} FAIL"


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

    if screen == ScreenId.PING:
        if state.ping.running:
            return ["Ping in corso...", "", state.ping.message]
        if not state.ping.results:
            adhoc = state.ping.adhoc_host or "n/a"
            return [
                "8.8.8.8 + 1.1.1.1",
                f"Adhoc: {adhoc[:16]}",
                "",
                "○ esegui ping",
                "ndp test ping",
                "--adhoc HOST",
            ]
        lines = [
            _ping_line(
                item.label,
                item.host,
                item.result.reachable,
                item.result.rtt_ms,
                item.result.message,
            )
            for item in state.ping.results[:6]
        ]
        if state.ping.adhoc_host:
            lines.append(f"Adhoc {state.ping.adhoc_host[:16]}")
        lines.append("○ ripeti")
        return lines[:7]

    if screen == ScreenId.SYSTEM:
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

    return ["Discover screen"]
