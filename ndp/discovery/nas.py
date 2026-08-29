"""NAS discovery (Synology, QNAP, mDNS, SSDP)."""

from __future__ import annotations

import json
import logging
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ndp.discovery.mdns import discover_mdns_services
from ndp.discovery.ssdp import discover_ssdp_devices

logger = logging.getLogger(__name__)

_SYNOLOGY_PORT = 9997
_QNAP_PORT = 7777
_DEFAULT_TIMEOUT = 2.5
_NAS_MDNS_HINTS = ("synology", "qnap", "nas", "ds", "diskstation", "mycloud", "wdmycloud")
_NAS_SSDP_HINTS = ("synology", "qnap", "nas", "diskstation", "readynas", "netgear")


@dataclass
class NasDevice:
    name: str
    source: str
    host: str | None = None
    model: str | None = None
    version: str | None = None
    serial: str | None = None
    protocols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _probe_synology(interface: str, *, timeout_seconds: float) -> list[NasDevice]:
    devices: list[NasDevice] = []
    request = json.dumps({"version": 1, "cmd": "getServerInfo"}).encode("utf-8")
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(timeout_seconds)
        sock.sendto(request, ("255.255.255.255", _SYNOLOGY_PORT))
        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            try:
                payload = json.loads(data.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            devices.append(
                NasDevice(
                    name=str(payload.get("hostname") or payload.get("host") or f"Synology {addr[0]}"),
                    source="Synology",
                    host=str(payload.get("ip") or addr[0]),
                    model=str(payload.get("model") or payload.get("modelname") or "") or None,
                    version=str(payload.get("version") or "") or None,
                    serial=str(payload.get("serial") or "") or None,
                    protocols=["Synology UDP/9997"],
                )
            )
    except OSError as exc:
        logger.debug("Synology discovery failed: %s", exc)
    finally:
        if sock is not None:
            sock.close()
    return devices


def _probe_qnap(interface: str, *, timeout_seconds: float) -> list[NasDevice]:
    devices: list[NasDevice] = []
    request = json.dumps({"data": {"type": "discover", "data": {}}}).encode("utf-8")
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(timeout_seconds)
        sock.sendto(request, ("255.255.255.255", _QNAP_PORT))
        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            if "qnap" not in text.lower() and "nas" not in text.lower():
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {"raw": text}
            name = None
            model = None
            if isinstance(payload, dict):
                inner = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                if isinstance(inner, dict):
                    name = inner.get("hostname") or inner.get("name")
                    model = inner.get("model") or inner.get("modelName")
            devices.append(
                NasDevice(
                    name=str(name or f"QNAP {addr[0]}"),
                    source="QNAP",
                    host=addr[0],
                    model=str(model) if model else None,
                    protocols=["QNAP UDP/7777"],
                )
            )
    except OSError as exc:
        logger.debug("QNAP discovery failed: %s", exc)
    finally:
        if sock is not None:
            sock.close()
    return devices
    blob = f"{service.name} {service.service_type} {service.host}".lower()
    if not any(hint in blob for hint in _NAS_MDNS_HINTS):
        return None
    return NasDevice(
        name=service.name or service.service_type,
        source="mDNS",
        host=service.host,
        model=service.txt.get("model"),
        protocols=["mDNS"],
    )


def _nas_from_ssdp(device) -> NasDevice | None:
    blob = " ".join(part for part in (device.usn, device.st, device.server) if part).lower()
    if not any(hint in blob for hint in _NAS_SSDP_HINTS):
        return None
    return NasDevice(
        name=device.usn or device.st or f"NAS {device.host}",
        source="SSDP",
        host=device.host,
        protocols=["SSDP/UPnP"],
    )


def discover_nas_devices(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[NasDevice]:
    found: dict[str, NasDevice] = {}

    for device in _probe_synology(interface, timeout_seconds=timeout_seconds):
        key = f"syno|{device.host}|{device.serial}"
        found[key] = device

    for device in _probe_qnap(interface, timeout_seconds=timeout_seconds):
        key = f"qnap|{device.host}|{device.name}"
        found[key] = device

    for service in discover_mdns_services(interface, timeout_seconds=timeout_seconds):
        device = _nas_from_mdns(service)
        if device is None:
            continue
        key = f"mdns|{device.name}|{device.host}"
        found[key] = device

    for ssdp in discover_ssdp_devices(interface, timeout_seconds=timeout_seconds):
        device = _nas_from_ssdp(ssdp)
        if device is None:
            continue
        key = f"ssdp|{device.host}|{device.name}"
        found[key] = device

    return list(found.values())


def discover_nas_snapshot(interface: str, *, timeout_seconds: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    devices = discover_nas_devices(interface, timeout_seconds=timeout_seconds)
    return {
        "interface": interface,
        "timeout_seconds": timeout_seconds,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "device_count": len(devices),
        "protocols": ["Synology UDP/9997", "QNAP UDP/7777", "mDNS", "SSDP/UPnP"],
        "devices": [device.to_dict() for device in devices],
        "note": (
            "Synology Assistant e Qfinder usano protocolli simili; altri NAS possono "
            "comparire solo via mDNS/SSDP se non espongono discovery UDP."
        ),
    }
