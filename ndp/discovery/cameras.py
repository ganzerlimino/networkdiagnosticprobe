"""IP camera discovery (ONVIF, SADP, Dahua, mDNS, SSDP)."""

from __future__ import annotations

import logging
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

from ndp.discovery.dahua_discover import discover_dahua_cameras
from ndp.discovery.hikvision_sadp import discover_hikvision_sadp
from ndp.discovery.mdns import discover_mdns_services
from ndp.discovery.ssdp import discover_ssdp_devices

logger = logging.getLogger(__name__)

_ONVIF_ADDR = ("239.255.255.250", 3702)
_DEFAULT_TIMEOUT = 2.5
_CAMERA_MDNS_TYPES = (
    "_onvif._tcp.local",
    "_rtsp._tcp.local",
    "_axis-video._tcp.local",
    "_http._tcp.local",
)
_CAMERA_SSDP_HINTS = ("camera", "onvif", "ipcam", "hikvision", "dahua", "axis", "reolink", "foscam")

_ONVIF_PROBE = b"""<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header>
<w:MessageID>uuid:ndp-onvif-probe</w:MessageID>
<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
</e:Header>
<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>"""


@dataclass
class CameraDevice:
    name: str
    source: str
    host: str | None = None
    port: int | None = None
    service_url: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    protocols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_onvif_probe_match(payload: str, source_host: str) -> CameraDevice | None:
    if "ProbeMatches" not in payload and "ProbeMatch" not in payload:
        return None
    xaddrs: list[str] = []
    scopes: list[str] = []
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None

    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "XAddrs" and elem.text:
            xaddrs.extend(part.strip() for part in elem.text.split() if part.strip())
        if tag == "Scopes" and elem.text:
            scopes.extend(part.strip() for part in elem.text.split() if part.strip())

    manufacturer = None
    model = None
    for scope in scopes:
        if "/name/" in scope:
            model = scope.rsplit("/", 1)[-1]
        if "/hardware/" in scope:
            manufacturer = scope.rsplit("/", 1)[-1]

    name = model or manufacturer or f"ONVIF {source_host}"
    service_url = xaddrs[0] if xaddrs else None
    return CameraDevice(
        name=name,
        source="ONVIF",
        host=source_host,
        service_url=service_url,
        manufacturer=manufacturer,
        model=model,
        protocols=["ONVIF"],
    )


def discover_onvif_cameras(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[CameraDevice]:
    devices: list[CameraDevice] = []
    seen: set[str] = set()
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(timeout_seconds)
        sock.sendto(_ONVIF_PROBE, _ONVIF_ADDR)
        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            device = _parse_onvif_probe_match(text, addr[0])
            if device is None:
                continue
            key = device.service_url or device.host or device.name
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
    except OSError as exc:
        logger.warning("ONVIF discovery failed on %s: %s", interface, exc)
    finally:
        if sock is not None:
            sock.close()
    return devices


def _camera_from_mdns(service) -> CameraDevice | None:
    service_type = (service.service_type or "").lower()
    name = service.name or service.service_type
    if not any(token in service_type for token in ("onvif", "rtsp", "axis-video")):
        if service_type.endswith("_http._tcp.local"):
            if not re.search(r"cam|ipc|dvr|nvr|hik|dahua|axis|reolink", name.lower()):
                return None
        else:
            return None
    protocols = []
    if "onvif" in service_type:
        protocols.append("ONVIF/mDNS")
    if "rtsp" in service_type:
        protocols.append("RTSP/mDNS")
    if "axis-video" in service_type:
        protocols.append("Axis/mDNS")
    if not protocols:
        protocols.append("mDNS")
    return CameraDevice(
        name=name,
        source="mDNS",
        host=service.host,
        port=service.port,
        manufacturer=service.txt.get("manufacturer") or service.txt.get("vendor"),
        model=service.txt.get("model"),
        protocols=protocols,
    )


def _camera_from_ssdp(device) -> CameraDevice | None:
    blob = " ".join(
        part
        for part in (device.usn, device.st, device.server, device.location)
        if part
    ).lower()
    if not any(hint in blob for hint in _CAMERA_SSDP_HINTS):
        return None
    return CameraDevice(
        name=device.usn or device.st or f"SSDP {device.host}",
        source="SSDP",
        host=device.host,
        service_url=device.location,
        protocols=["SSDP/UPnP"],
    )


def discover_cameras(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[CameraDevice]:
    found: dict[str, CameraDevice] = {}

    for device in discover_onvif_cameras(interface, timeout_seconds=timeout_seconds):
        key = f"onvif|{device.host}|{device.service_url}"
        found[key] = device

    for sadp in discover_hikvision_sadp(interface, timeout_seconds=timeout_seconds):
        fields = sadp.to_camera_fields()
        key = f"sadp|{fields['host']}|{fields.get('model')}"
        found[key] = CameraDevice(**fields)

    for dahua in discover_dahua_cameras(interface, timeout_seconds=timeout_seconds):
        fields = dahua.to_camera_fields()
        key = f"dahua|{fields['host']}|{dahua.serial or fields.get('model')}"
        found[key] = CameraDevice(**fields)

    for service in discover_mdns_services(interface, timeout_seconds=timeout_seconds):
        device = _camera_from_mdns(service)
        if device is None:
            continue
        key = f"mdns|{device.name}|{device.host}|{device.port}"
        found[key] = device

    for ssdp in discover_ssdp_devices(interface, timeout_seconds=timeout_seconds):
        device = _camera_from_ssdp(ssdp)
        if device is None:
            continue
        key = f"ssdp|{device.host}|{device.name}"
        found[key] = device

    return list(found.values())


def discover_cameras_snapshot(interface: str, *, timeout_seconds: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    devices = discover_cameras(interface, timeout_seconds=timeout_seconds)
    return {
        "interface": interface,
        "timeout_seconds": timeout_seconds,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "device_count": len(devices),
        "protocols": [
            "ONVIF WS-Discovery",
            "Hikvision SADP (UDP/37020)",
            "Dahua DHDiscover (UDP/37810)",
            "mDNS (_onvif/_rtsp/_axis-video)",
            "SSDP/UPnP",
        ],
        "devices": [device.to_dict() for device in devices],
        "note": (
            "SADP e DHDiscover trovano telecamere anche con ONVIF disabilitato. "
            "Risultati deduplicati per host/protocollo."
        ),
    }
