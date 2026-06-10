"""Simple console renderer for headless development and appliances."""

from __future__ import annotations

from ndp.core.state import ProbeState


def _fmt(value: object, fallback: str = "n/a") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def render_status(state: ProbeState) -> str:
    lines = [
        "=== Network Diagnostic Probe ===",
        f"Interface : {state.interface}",
        f"Updated   : {state.updated_at.isoformat()}",
        "",
        "[ Link ]",
        f"  State   : {_fmt(state.link.operstate)}",
        f"  Carrier : {'yes' if state.link.carrier else 'no'}",
        f"  Speed   : {_fmt(state.link.speed_mbps, 'unknown')} Mbps",
        f"  Duplex  : {_fmt(state.link.duplex)}",
        f"  MAC     : {_fmt(state.link.mac_address)}",
        "",
        "[ Neighbor ]",
        f"  Protocol: {_fmt(state.neighbor.protocol)}",
        f"  Switch  : {_fmt(state.neighbor.switch_name)}",
        f"  Port    : {_fmt(state.neighbor.port_id)}",
        f"  VLAN    : {_fmt(state.neighbor.vlan_id)}",
        f"  Status  : {_fmt(state.neighbor.message)}",
        "",
        "[ IP ]",
    ]

    if state.ip.addresses:
        for addr in state.ip.addresses:
            lines.append(f"  {addr.family:>4} : {addr.address}/{addr.prefixlen}")
    else:
        lines.append("  (no addresses)")

    lines.extend(
        [
            f"  Gateway : {_fmt(state.ip.gateway)}",
            f"  DNS     : {', '.join(state.ip.dns_servers) if state.ip.dns_servers else 'n/a'}",
            "",
            "[ System ]",
            f"  Hostname: {_fmt(state.system.hostname)}",
            f"  Uptime  : {_fmt(state.system.uptime_seconds, 'unknown')} s",
            f"  CPU temp: {_fmt(state.system.cpu_temperature_c, 'unknown')} C",
        ]
    )

    return "\n".join(lines)
