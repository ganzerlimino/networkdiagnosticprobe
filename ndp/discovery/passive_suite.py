"""Combined passive check API snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ndp.discovery.dhcp_option82 import sniff_dhcp_option82
from ndp.discovery.ethertype_probe import probe_l2_snapshot
from ndp.discovery.mdns import discover_mdns_snapshot
from ndp.discovery.passive_check import sniff_passive_protocols
from ndp.discovery.snmp_probe import probe_snmp_snapshot
from ndp.discovery.ssdp import discover_ssdp_snapshot


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
    mdns = discover_mdns_snapshot(interface)
    ssdp = discover_ssdp_snapshot(interface)
    l2_probes = probe_l2_snapshot(interface)

    return {
        "interface": interface,
        "listen_seconds": listen_seconds,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "l2_passive": l2.to_dict(),
        "dhcp_option82": dhcp.to_dict(),
        "snmp": snmp,
        "mdns": mdns,
        "ssdp": ssdp,
        "l2_probes": l2_probes,
        "summary": _build_summary(l2.to_dict(), mdns, ssdp, l2_probes, dhcp.to_dict()),
    }


def _build_summary(
    l2: dict[str, Any],
    mdns: dict[str, Any],
    ssdp: dict[str, Any],
    l2_probes: dict[str, Any],
    dhcp: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hit in l2.get("hits", []):
        rows.append(
            {
                "protocol": hit.get("protocol"),
                "category": "L2 broadcast",
                "status": "detected",
                "detail": f"{hit.get('frame_count', 0)} frame · {hit.get('variant')}",
            }
        )
    for hit in l2_probes.get("hits", []):
        rows.append(
            {
                "protocol": hit.get("protocol"),
                "category": "L2 ethertype",
                "status": "detected",
                "detail": f"{hit.get('frame_count', 0)} frame",
            }
        )
    rows.append(
        {
            "protocol": "mDNS",
            "category": "service discovery",
            "status": "ok" if mdns.get("service_count", 0) else "none",
            "detail": f"{mdns.get('service_count', 0)} servizi",
        }
    )
    rows.append(
        {
            "protocol": "SSDP",
            "category": "service discovery",
            "status": "ok" if ssdp.get("device_count", 0) else "none",
            "detail": f"{ssdp.get('device_count', 0)} dispositivi",
        }
    )
    rows.append(
        {
            "protocol": "DHCP Option 82",
            "category": "DHCP",
            "status": "ok" if dhcp.get("sample_count", 0) else "none",
            "detail": f"{dhcp.get('sample_count', 0)} campioni",
        }
    )
    return rows
