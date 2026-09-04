"""Text reports for email export from the mobile web UI."""

from __future__ import annotations

from datetime import datetime, timezone

from ndp.core.state import ProbeState
from ndp.discovery.console import render_updown_result
from ndp.discovery.wizard import UpDownResult
from ndp.locale.loader import load_locale, translate
from ndp.scan.dns import NetworkDiagnosticsResult
from ndp.scan.ports import PortScanResult


def _fmt(value: object, fallback: str = "n/a") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _t(locale: dict[str, object], key: str, **variables: object) -> str:
    return translate(locale, key, **variables)


def _section_status(state: ProbeState, locale: dict[str, object]) -> list[str]:
    link = state.link
    ip = state.ip
    neighbor = state.neighbor
    system = state.system
    status_up = _t(locale, "report.status_up")
    status_down = _t(locale, "report.status_down")
    lines = [
        _t(locale, "report.sec_link"),
        _t(locale, "report.link_status", status=status_up if link.carrier else status_down),
        _t(locale, "report.link_mac", value=_fmt(link.mac_address)),
        _t(locale, "report.link_speed", value=_fmt(link.speed_mbps))
        if link.speed_mbps
        else _t(locale, "report.link_speed_na"),
        "",
        _t(locale, "report.sec_network"),
    ]
    if ip.addresses:
        for addr in ip.addresses:
            lines.append(f"{addr.family} {addr.address}/{addr.prefixlen}")
    else:
        lines.append(_t(locale, "report.no_address"))
    lines.extend(
        [
            _t(locale, "report.gateway", value=_fmt(ip.gateway)),
            _t(locale, "report.dns_servers", value=", ".join(ip.dns_servers) if ip.dns_servers else "n/a"),
            "",
            _t(locale, "report.sec_switch"),
        ]
    )
    if neighbor.available:
        lines.extend(
            [
                _t(locale, "report.protocol", value=_fmt(neighbor.protocol)),
                _t(locale, "report.switch_name", value=_fmt(neighbor.switch_name)),
                _t(locale, "report.port", value=_fmt(neighbor.port_id)),
                _t(locale, "report.vlan", value=_fmt(neighbor.vlan_id)),
            ]
        )
    else:
        lines.append(_fmt(neighbor.message, _t(locale, "report.waiting")))
    lines.extend(
        [
            "",
            _t(locale, "report.sec_system"),
            _t(locale, "report.hostname", value=_fmt(system.hostname)),
            _t(locale, "report.uptime", value=_fmt(system.uptime_seconds)),
            _t(locale, "report.temperature", value=_fmt(system.cpu_temperature_c)),
            _t(locale, "report.interface", value=state.interface),
        ]
    )
    return lines


def _section_ping(state: ProbeState, locale: dict[str, object]) -> list[str]:
    ping = state.ping
    lines = [_t(locale, "report.sec_ping")]
    if ping.running:
        lines.append(ping.message or _t(locale, "report.ping_running"))
        return lines
    if not ping.results:
        lines.append(_t(locale, "report.no_ping"))
        if ping.adhoc_host:
            lines.append(_t(locale, "report.adhoc_host", host=ping.adhoc_host))
        return lines
    for item in ping.results:
        result = item.result
        rtt = f"{result.rtt_ms:.1f} ms" if result.rtt_ms is not None else _t(locale, "report.status_fail")
        status = _t(locale, "report.status_ok") if result.reachable else _t(locale, "report.status_fail")
        lines.append(f"{item.label} {item.host}: {status} ({rtt})")
    if ping.last_run_at:
        lines.append(_t(locale, "report.last_run", timestamp=ping.last_run_at.isoformat()))
    return lines


def _section_discover(result: UpDownResult | None, locale: dict[str, object]) -> list[str]:
    lines = [_t(locale, "report.sec_discover")]
    if result is None:
        lines.append(_t(locale, "report.no_wizard"))
        return lines
    lines.append(render_updown_result(result))
    return lines


def _section_scan(scan: PortScanResult | None, locale: dict[str, object]) -> list[str]:
    lines = [_t(locale, "report.sec_scan")]
    if scan is None:
        lines.append(_t(locale, "report.no_scan"))
        return lines
    lines.append(_t(locale, "report.host", value=scan.host))
    lines.append(_t(locale, "report.profile", value=scan.profile))
    lines.append(
        _t(
            locale,
            "report.open_ports_count",
            open=len(scan.open_ports),
            total=len(scan.entries),
        )
    )
    for entry in scan.open_ports:
        latency = f" ({entry.latency_ms:.0f} ms)" if entry.latency_ms else ""
        lines.append(f"  {entry.port}/tcp {entry.service}{latency}")
    if not scan.open_ports:
        lines.append(f"  {_t(locale, 'report.no_open_ports')}")
    return lines


def _section_network(diag: NetworkDiagnosticsResult | None, locale: dict[str, object]) -> list[str]:
    lines = [_t(locale, "report.sec_dns")]
    if diag is None:
        lines.append(_t(locale, "report.no_network_check"))
        return lines
    for lookup in diag.lookups:
        if lookup.addresses:
            lines.append(
                _t(
                    locale,
                    "report.lookup_ok",
                    hostname=lookup.hostname,
                    addresses=", ".join(lookup.addresses),
                )
            )
        else:
            lines.append(
                _t(
                    locale,
                    "report.lookup_fail",
                    hostname=lookup.hostname,
                    error=lookup.error or "n/a",
                )
            )
    for server in diag.dns_servers:
        status = (
            _t(locale, "report.status_ok")
            if server.resolves
            else ("TCP/53" if server.reachable_tcp_53 else _t(locale, "report.status_fail"))
        )
        lines.append(_t(locale, "report.dns_server", server=server.server, status=status))
    if diag.gateway is not None:
        gw = diag.gateway
        if gw.ping_reachable and gw.ping_rtt_ms:
            ping = f"{_t(locale, 'report.status_ok')} {gw.ping_rtt_ms:.0f}ms"
        else:
            ping = _t(locale, "report.status_fail")
        lines.append(_t(locale, "report.gateway_ping", gateway=gw.gateway, status=ping))
        if gw.open_ports:
            ports = ", ".join(f"{p.port}/{p.service}" for p in gw.open_ports)
            lines.append(_t(locale, "report.gateway_ports", ports=ports))
    return lines


def build_report(
    state: ProbeState,
    *,
    section: str = "all",
    discovery_result: UpDownResult | None = None,
    scan_result: PortScanResult | None = None,
    network_diag: NetworkDiagnosticsResult | None = None,
    version: str = "0.0.0",
    locale_code: str = "it",
) -> dict[str, str]:
    section = section.lower().strip()
    locale = load_locale(locale_code)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        _t(locale, "report.title"),
        _t(locale, "report.version", version=version),
        _t(locale, "report.generated", timestamp=now),
        "",
    ]

    body_parts: list[str] = []
    subject = _t(locale, "report.subject_full")

    if section in {"status", "stato", "all", "tutto"}:
        if section in {"status", "stato"}:
            subject = _t(locale, "report.subject_status")
        body_parts.extend(_section_status(state, locale))

    if section in {"ping", "all", "tutto"}:
        if section == "ping":
            subject = _t(locale, "report.subject_ping")
        if body_parts:
            body_parts.append("")
        body_parts.extend(_section_ping(state, locale))

    if section in {"discover", "discovery", "all", "tutto"}:
        if section in {"discover", "discovery"}:
            subject = _t(locale, "report.subject_discover")
        if body_parts:
            body_parts.append("")
        body_parts.extend(_section_discover(discovery_result, locale))

    if section in {"scan", "porte", "ports", "all", "tutto"}:
        if section in {"scan", "porte", "ports"}:
            subject = _t(locale, "report.subject_scan")
        if body_parts:
            body_parts.append("")
        body_parts.extend(_section_scan(scan_result, locale))

    if section in {"network", "dns", "gateway", "all", "tutto"}:
        if section in {"network", "dns", "gateway"}:
            subject = _t(locale, "report.subject_network")
        if body_parts:
            body_parts.append("")
        body_parts.extend(_section_network(network_diag, locale))

    if section in {"all", "tutto"}:
        subject = _t(locale, "report.subject_full")

    if not body_parts:
        body_parts = _section_status(state, locale)
        subject = _t(locale, "report.subject_status")

    body = "\n".join(header + body_parts)
    if len(body) > 6000:
        body = body[:5990] + "\n" + _t(locale, "report.truncated")

    return {"subject": subject, "body": body}
