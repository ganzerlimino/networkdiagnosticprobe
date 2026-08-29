"""Combined passive check API snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ndp.discovery.dhcp_option82 import sniff_dhcp_option82
from ndp.discovery.passive_check import sniff_passive_protocols
from ndp.discovery.snmp_probe import probe_snmp_snapshot


def run_passive_check_suite(
    interface: str,
    *,
    listen_seconds: float = 3.0,
    snmp_host: str | None = None,
    gateway: str | None = None,
) -> dict[str, Any]:
    l2 = sniff_passive_protocols(interface, listen_seconds=listen_seconds)
    dhcp = sniff_dhcp_option82(interface, listen_seconds=listen_seconds)
    snmp = probe_snmp_snapshot(snmp_host, gateway=gateway)

    return {
        "interface": interface,
        "listen_seconds": listen_seconds,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "l2_passive": l2.to_dict(),
        "dhcp_option82": dhcp.to_dict(),
        "snmp": snmp,
    }
