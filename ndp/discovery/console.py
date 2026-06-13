"""Console rendering for discovery workflows."""

from __future__ import annotations

from ndp.discovery.diff import ScanDiff
from ndp.discovery.host import DiscoveredHost, ScanSnapshot
from ndp.discovery.wizard import UpDownResult


def _fmt(value: object, fallback: str = "n/a") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def render_host(host: DiscoveredHost) -> str:
    vendor = f" ({host.vendor})" if host.vendor else ""
    return f"  {host.ip:>15}  {host.mac}  {vendor}"


def render_snapshot(snapshot: ScanSnapshot) -> str:
    lines = [
        f"Scan on {snapshot.interface} @ {snapshot.scanned_at.isoformat()}",
        f"Source: {snapshot.source} — {snapshot.host_count} host(s)",
    ]
    if snapshot.hosts:
        lines.append("")
        for host in snapshot.hosts:
            lines.append(render_host(host))
    else:
        lines.append("  (nessun host trovato)")
    return "\n".join(lines)


def render_diff(diff: ScanDiff) -> str:
    lines = [
        "=== Risultato Up/Down ===",
        f"Dispositivi scomparsi: {diff.offline_count}",
        f"Nuovi dispositivi  : {len(diff.online_hosts)}",
        f"Invariati           : {len(diff.unchanged_hosts)}",
        "",
    ]

    if not diff.offline_hosts:
        lines.append("Nessun dispositivo è andato offline.")
        if diff.online_hosts:
            lines.append("Attenzione: comparsi nuovi host — ripeti con un solo device scollegato.")
        return "\n".join(lines)

    if diff.probable_match:
        host = diff.probable_match
        lines.extend(
            [
                ">>> PROBABILE MATCH (unico device scomparso) <<<",
                render_host(host),
                "",
            ]
        )
    else:
        lines.append("Device andati offline:")
        for host in diff.offline_hosts:
            lines.append(render_host(host))
        lines.append("")
        lines.append("Più device scomparsi: scollega un solo apparato per volta.")

    if diff.online_hosts:
        lines.extend(["", "Nuovi host rilevati:"])
        for host in diff.online_hosts:
            lines.append(render_host(host))

    return "\n".join(lines)


def render_updown_result(result: UpDownResult) -> str:
    sections = [
        render_diff(result.diff),
    ]

    if result.verify is not None:
        sections.extend(
            [
                "",
                "=== Verifica ricollegamento ===",
                f"Host confermati: {len(result.confirmed_hosts)}",
            ]
        )
        if result.confirmed_hosts:
            for host in result.confirmed_hosts:
                sections.append(render_host(host))
            sections.append("")
            sections.append("Il dispositivo ricollegato corrisponde a un host scomparso.")
        elif result.diff.offline_hosts:
            sections.append("Nessun host scomparso è ricomparso — verifica il collegamento.")

    return "\n".join(sections)
