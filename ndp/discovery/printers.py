"""Network printer discovery (Epson ENPC retail, Zebra Link-OS industrial)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ndp.discovery.epson_enpc import discover_epson_enpc
from ndp.discovery.zebra_discovery import discover_zebra_printers

_DEFAULT_TIMEOUT = 3.0


@dataclass
class PrinterDevice:
    name: str
    vendor: str
    source: str
    category: str
    host: str | None = None
    mac: str | None = None
    model: str | None = None
    hostname: str | None = None
    protocols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_printers(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[PrinterDevice]:
    found: dict[str, PrinterDevice] = {}

    for device in discover_epson_enpc(interface, timeout_seconds=timeout_seconds):
        fields = device.to_printer_fields()
        key = f"epson|{fields.get('mac') or fields['host']}|{fields.get('model') or ''}"
        found[key] = PrinterDevice(**fields)

    for device in discover_zebra_printers(interface, timeout_seconds=timeout_seconds):
        fields = device.to_printer_fields()
        key = f"zebra|{fields.get('hostname') or fields['host']}|{fields.get('model') or ''}"
        found[key] = PrinterDevice(**fields)

    return sorted(found.values(), key=lambda item: (item.vendor, item.name, item.host or ""))


def discover_printers_snapshot(interface: str, *, timeout_seconds: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    devices = discover_printers(interface, timeout_seconds=timeout_seconds)
    epson_count = sum(1 for device in devices if device.vendor == "Epson")
    zebra_count = sum(1 for device in devices if device.vendor == "Zebra")
    return {
        "interface": interface,
        "timeout_seconds": timeout_seconds,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "device_count": len(devices),
        "epson_count": epson_count,
        "zebra_count": zebra_count,
        "protocols": [
            "Epson ENPC (UDP/3289)",
            "Zebra Link-OS discovery (UDP/4201)",
        ],
        "devices": [device.to_dict() for device in devices],
        "note": (
            "Epson ENPC copre stampanti receipt/fiscali retail. "
            "Zebra UDP/4201 copre stampanti etichette Link-OS. "
            "Discovery può essere disabilitato sulla stampante o filtrato dal firewall."
        ),
    }
