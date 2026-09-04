"""Combined passive check API snapshot."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from ndp.discovery.dhcp_option82 import sniff_dhcp_option82
from ndp.discovery.ethertype_probe import probe_l2_protocols
from ndp.discovery.mdns import discover_mdns_snapshot
from ndp.discovery.passive_check import sniff_passive_protocols
from ndp.discovery.snmp_probe import probe_snmp_snapshot
from ndp.discovery.ssdp import discover_ssdp_snapshot


def _service_timeout(listen_seconds: float) -> float:
    return min(max(listen_seconds * 0.4, 1.5), 6.0)


def _l2_probe_seconds(listen_seconds: float) -> float:
    return min(max(listen_seconds * 0.2, 1.0), listen_seconds)


def run_passive_check_suite(
    interface: str,
    *,
    listen_seconds: float = 3.0,
    snmp_host: str | None = None,
    gateway: str | None = None,
) -> dict[str, Any]:
    """Run passive probes. Sniff/mDNS/SSDP/SNMP phases execute in parallel (~listen_seconds wall time)."""
    started = time.monotonic()
    service_timeout = _service_timeout(listen_seconds)
    l2_probe_seconds = _l2_probe_seconds(listen_seconds)

    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="ndp-passive") as pool:
        future_l2 = pool.submit(
            sniff_passive_protocols, interface, listen_seconds=listen_seconds
        )
        future_dhcp = pool.submit(
            sniff_dhcp_option82, interface, listen_seconds=listen_seconds
        )
        future_snmp = pool.submit(probe_snmp_snapshot, snmp_host, gateway=gateway)
        future_mdns = pool.submit(
            discover_mdns_snapshot, interface, timeout_seconds=service_timeout
        )
        future_ssdp = pool.submit(
            discover_ssdp_snapshot, interface, timeout_seconds=service_timeout
        )
        future_l2_probe = pool.submit(
            probe_l2_protocols, interface, listen_seconds=l2_probe_seconds
        )

        l2 = future_l2.result()
        dhcp = future_dhcp.result()
        snmp = future_snmp.result()
        mdns = future_mdns.result()
        ssdp = future_ssdp.result()
        l2_hits = future_l2_probe.result()

    duration_seconds = round(time.monotonic() - started, 2)
    l2_probes = {
        "interface": interface,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "hits": [hit.to_dict() for hit in l2_hits],
    }

    return {
        "interface": interface,
        "listen_seconds": listen_seconds,
        "duration_seconds": duration_seconds,
        "parallel": True,
        "note": (
            "Le fasi L2/DHCP/mDNS/SSDP/SNMP vengono eseguite in parallelo: "
            f"la durata effettiva è ~{listen_seconds:g}s, non il totale delle singole fasi."
        ),
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
