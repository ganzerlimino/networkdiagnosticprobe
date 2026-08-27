"""Text reports for email export from the mobile web UI."""

from __future__ import annotations

from datetime import datetime, timezone

from ndp.core.state import ProbeState
from ndp.discovery.console import render_updown_result
from ndp.discovery.wizard import UpDownResult


def _fmt(value: object, fallback: str = "n/a") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _section_status(state: ProbeState) -> list[str]:
    link = state.link
    ip = state.ip
    neighbor = state.neighbor
    system = state.system
    lines = [
        "=== LINK ===",
        f"Stato: {'UP' if link.carrier else 'DOWN'}",
        f"MAC: {_fmt(link.mac_address)}",
        f"Velocità: {_fmt(link.speed_mbps)} Mbps" if link.speed_mbps else "Velocità: n/a",
        "",
        "=== RETE ===",
    ]
    if ip.addresses:
        for addr in ip.addresses:
            lines.append(f"{addr.family} {addr.address}/{addr.prefixlen}")
    else:
        lines.append("Nessun indirizzo IP")
    lines.extend(
        [
            f"Gateway: {_fmt(ip.gateway)}",
            f"DNS: {', '.join(ip.dns_servers) if ip.dns_servers else 'n/a'}",
            "",
            "=== SWITCH / LLDP ===",
        ]
    )
    if neighbor.available:
        lines.extend(
            [
                f"Protocollo: {_fmt(neighbor.protocol)}",
                f"Switch: {_fmt(neighbor.switch_name)}",
                f"Porta: {_fmt(neighbor.port_id)}",
                f"VLAN: {_fmt(neighbor.vlan_id)}",
            ]
        )
    else:
        lines.append(_fmt(neighbor.message, "In attesa"))
    lines.extend(
        [
            "",
            "=== SISTEMA ===",
            f"Hostname: {_fmt(system.hostname)}",
            f"Uptime: {_fmt(system.uptime_seconds)} s",
            f"Temperatura: {_fmt(system.cpu_temperature_c)} °C",
            f"Interfaccia: {state.interface}",
        ]
    )
    return lines


def _section_ping(state: ProbeState) -> list[str]:
    ping = state.ping
    lines = ["=== PING ==="]
    if ping.running:
        lines.append(ping.message or "In corso...")
        return lines
    if not ping.results:
        lines.append("Nessun risultato ping salvato.")
        if ping.adhoc_host:
            lines.append(f"Host ad-hoc configurato: {ping.adhoc_host}")
        return lines
    for item in ping.results:
        result = item.result
        rtt = f"{result.rtt_ms:.1f} ms" if result.rtt_ms is not None else "FAIL"
        status = "OK" if result.reachable else "FAIL"
        lines.append(f"{item.label} {item.host}: {status} ({rtt})")
    if ping.last_run_at:
        lines.append(f"Ultimo run: {ping.last_run_at.isoformat()}")
    return lines


def _section_discover(result: UpDownResult | None) -> list[str]:
    lines = ["=== DISCOVER UP/DOWN ==="]
    if result is None:
        lines.append("Nessun wizard completato in questa sessione.")
        return lines
    lines.append(render_updown_result(result))
    return lines


def build_report(
    state: ProbeState,
    *,
    section: str = "all",
    discovery_result: UpDownResult | None = None,
    version: str = "0.0.0",
) -> dict[str, str]:
    section = section.lower().strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        "Network Diagnostic Probe",
        f"Versione {version}",
        f"Generato: {now}",
        "",
    ]

    body_parts: list[str] = []
    subject = "NDP Report"

    if section in {"status", "stato", "all", "tutto"}:
        if section in {"status", "stato"}:
            subject = "NDP — Stato rete"
        body_parts.extend(_section_status(state))

    if section in {"ping", "all", "tutto"}:
        if section == "ping":
            subject = "NDP — Ping"
        if body_parts:
            body_parts.append("")
        body_parts.extend(_section_ping(state))

    if section in {"discover", "discovery", "all", "tutto"}:
        if section in {"discover", "discovery"}:
            subject = "NDP — Discover"
        if body_parts:
            body_parts.append("")
        body_parts.extend(_section_discover(discovery_result))

    if section == "all" or section == "tutto":
        subject = "NDP — Report completo"

    if not body_parts:
        body_parts = _section_status(state)
        subject = "NDP — Stato rete"

    body = "\n".join(header + body_parts)
    if len(body) > 6000:
        body = body[:5990] + "\n...(troncato)"

    return {"subject": subject, "body": body}
