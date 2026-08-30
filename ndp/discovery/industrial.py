"""Industrial OT discovery: Weintek HMI, eWON gateways, management ports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ndp.discovery.ewon import discover_ewon_devices
from ndp.discovery.weintek_hmi import discover_weintek_hmi
from ndp.scan.ports import scan_ports


def discover_industrial_snapshot(
    interface: str,
    *,
    timeout_seconds: float = 3.0,
    host: str | None = None,
    include_port_profile: bool = False,
    port_timeout_seconds: float = 1.5,
) -> dict[str, Any]:
    weintek = discover_weintek_hmi(
        interface,
        timeout_seconds=timeout_seconds,
        port_timeout_seconds=min(port_timeout_seconds, 1.0),
    )
    ewon = discover_ewon_devices(
        interface,
        timeout_seconds=timeout_seconds,
        port_timeout_seconds=min(port_timeout_seconds, 1.0),
    )

    port_scan: dict[str, Any] | None = None
    if include_port_profile and host and host.strip():
        port_scan = scan_ports(
            host.strip(),
            "industrial",
            timeout_seconds=port_timeout_seconds,
        ).to_dict()

    return {
        "interface": interface,
        "timeout_seconds": timeout_seconds,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "weintek": {
            "count": len(weintek),
            "devices": [device.to_dict() for device in weintek],
            "protocols": [
                "HMI Search UDP/59999→60000",
                "Search for HMI UDP/10275",
                "EasyBuilder Find HMI UDP/20249",
            ],
            "management_ports": [8000, 8001, 5900],
        },
        "ewon": {
            "count": len(ewon),
            "devices": [device.to_dict() for device in ewon],
            "protocols": [
                "eBuddy IPCONF UDP/1507",
                "Alternate UDP/1234,4242",
                "OUI HMS 00:05:F5, 00:1E:C0",
            ],
            "management_ports": [80, 443, 21],
        },
        "device_count": len(weintek) + len(ewon),
        "port_scan": port_scan,
        "note": (
            "Discovery broadcast Weintek HMI Search ed eWON IPCONF con verifica porte "
            "di gestione (VNC/EasyAccess, HTTP/FTP)."
        ),
    }
