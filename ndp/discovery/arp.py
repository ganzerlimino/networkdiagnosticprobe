"""Active ARP discovery and neighbor cache management."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from ndp.core.subprocess_runner import CommandError, run_command, run_json_command
from ndp.discovery.host import DiscoveredHost, ScanSnapshot, normalize_mac
from ndp.discovery.oui import lookup_vendor, record_vendors_from_hosts

logger = logging.getLogger(__name__)

_ARP_SCAN_LINE = re.compile(
    r"^(?P<ip>\d+\.\d+\.\d+\.\d+)\s+(?P<mac>[0-9a-fA-F:.-]+)(?:\s+(?P<vendor>.+))?$"
)


def flush_arp_cache(interface: str) -> bool:
    """Drop kernel neighbor entries so the next scan reflects live hosts only."""
    try:
        run_command(["ip", "neigh", "flush", "dev", interface])
        logger.info("Flushed ARP/neighbor cache on %s", interface)
        return True
    except (CommandError, FileNotFoundError) as exc:
        logger.warning("Could not flush ARP cache on %s: %s", interface, exc)
        return False


def _parse_arp_scan_output(output: str, interface: str) -> list[DiscoveredHost]:
    hosts: list[DiscoveredHost] = []
    seen_macs: set[str] = set()

    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Interface:") or line.startswith("Starting"):
            continue
        if line.startswith("Ending") or line.startswith("packets"):
            continue

        match = _ARP_SCAN_LINE.match(line)
        if not match:
            continue

        mac = normalize_mac(match.group("mac"))
        if mac in seen_macs:
            continue
        seen_macs.add(mac)

        vendor = match.group("vendor")
        if not vendor:
            vendor = lookup_vendor(mac)

        hosts.append(
            DiscoveredHost(
                ip=match.group("ip"),
                mac=mac,
                vendor=vendor,
                source="arp-scan",
            )
        )

    hosts.sort(key=lambda host: (_ip_sort_key(host.ip), host.mac))
    return hosts


def _ip_sort_key(ip: str) -> tuple[int, int, int, int]:
    try:
        return tuple(int(part) for part in ip.split("."))
    except ValueError:
        return (255, 255, 255, 255)


def _scan_with_arp_scan(interface: str) -> list[DiscoveredHost]:
    output = run_command(
        [
            "arp-scan",
            f"--interface={interface}",
            "--localnet",
            "--ignoredups",
            "--plain",
        ],
        timeout=120.0,
    )
    return _parse_arp_scan_output(output, interface)


def _scan_with_ip_neigh(interface: str) -> list[DiscoveredHost]:
    data = run_json_command(["ip", "-j", "neigh", "show", "dev", interface])
    hosts: list[DiscoveredHost] = []

    if not isinstance(data, list):
        return hosts

    for entry in data:
        dst = entry.get("dst")
        lladdr = entry.get("lladdr")
        state = str(entry.get("state", "")).upper()
        if not dst or not lladdr:
            continue
        if "FAILED" in state or "INCOMPLETE" in state:
            continue

        mac = normalize_mac(str(lladdr))
        hosts.append(
            DiscoveredHost(
                ip=str(dst),
                mac=mac,
                vendor=lookup_vendor(mac),
                source="ip-neigh",
            )
        )

    hosts.sort(key=lambda host: (_ip_sort_key(host.ip), host.mac))
    return hosts


def scan_hosts(interface: str) -> ScanSnapshot:
    source = "arp-scan"
    hosts: list[DiscoveredHost] = []

    try:
        hosts = _scan_with_arp_scan(interface)
    except (CommandError, FileNotFoundError) as exc:
        logger.warning("arp-scan unavailable, falling back to ip neigh: %s", exc)
        source = "ip-neigh"
        try:
            hosts = _scan_with_ip_neigh(interface)
        except (CommandError, FileNotFoundError) as neigh_exc:
            logger.error("No ARP discovery method available: %s", neigh_exc)
            hosts = []

    snapshot = ScanSnapshot(
        interface=interface,
        hosts=hosts,
        scanned_at=datetime.now(timezone.utc),
        source=source,
    )
    record_vendors_from_hosts(snapshot.hosts)
    return snapshot
