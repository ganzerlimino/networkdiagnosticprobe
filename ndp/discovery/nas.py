"""NAS discovery (Synology, QNAP, ASUSTOR, ReadyNAS, WS-Discovery, mDNS, SSDP)."""

from __future__ import annotations

import json
import logging
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from xml.etree import ElementTree

from ndp.discovery.mdns import discover_mdns_services
from ndp.discovery.ssdp import discover_ssdp_devices

logger = logging.getLogger(__name__)

_SYNOLOGY_PORT = 9997
_QNAP_PORT = 7777
_ASUSTOR_PORTS = (8888, 8889)
_READYNAS_PORT = 22081
_WSD_ADDR = ("239.255.255.250", 3702)
_DEFAULT_TIMEOUT = 2.5

_READYNAS_PROBE = bytes.fromhex("0000073e0000000100000000f8d496c3ffffffff0000001c00000000")
_ASUSTOR_PROBES = (
    b"",
    b"ASUSTOR",
    json.dumps({"cmd": "search"}).encode("utf-8"),
    json.dumps({"type": "search", "id": 1}).encode("utf-8"),
)

_NAS_MDNS_HINTS = (
    "synology",
    "qnap",
    "nas",
    "ds",
    "diskstation",
    "mycloud",
    "wdmycloud",
    "asustor",
    "adm",
    "terramaster",
    "tnas",
    "readynas",
    "netgear",
    "buffalo",
    "ugreen",
    "zspace",
)
_NAS_SSDP_HINTS = (
    "synology",
    "qnap",
    "nas",
    "diskstation",
    "readynas",
    "netgear",
    "asustor",
    "terramaster",
    "mycloud",
    "western digital",
    "wd",
)

_WSD_PROBE = b"""<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devmgmt">
<e:Header>
<w:MessageID>uuid:ndp-nas-wsd-probe</w:MessageID>
<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
</e:Header>
<e:Body><d:Probe><d:Types>wsdp:Device</d:Types></d:Probe></e:Body>
</e:Envelope>"""


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


def _udp_broadcast_collect(
    interface: str,
    port: int,
    requests: bytes | tuple[bytes, ...],
    *,
    timeout_seconds: float,
    parse: Callable[[bytes, str], NasDevice | None],
) -> list[NasDevice]:
    devices: list[NasDevice] = []
    seen: set[str] = set()
    if isinstance(requests, bytes):
        requests = (requests,)
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
        for request in requests:
            sock.sendto(request, ("255.255.255.255", port))

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            device = parse(data, addr[0])
            if device is None:
                continue
            key = f"{device.host}|{device.serial or device.name}"
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
    except OSError as exc:
        logger.debug("UDP discovery on port %s failed: %s", port, exc)
    finally:
        if sock is not None:
            sock.close()
    return devices


def _parse_synology(data: bytes, addr: str) -> NasDevice | None:
    try:
        payload = json.loads(data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return NasDevice(
        name=str(payload.get("hostname") or payload.get("host") or f"Synology {addr}"),
        source="Synology",
        host=str(payload.get("ip") or addr),
        model=str(payload.get("model") or payload.get("modelname") or "") or None,
        version=str(payload.get("version") or "") or None,
        serial=str(payload.get("serial") or "") or None,
        protocols=["Synology UDP/9997"],
    )


def _parse_qnap(data: bytes, addr: str) -> NasDevice | None:
    text = data.decode("utf-8", errors="replace")
    if "qnap" not in text.lower() and "nas" not in text.lower():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    inner = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(inner, dict):
        inner = {}
    return NasDevice(
        name=str(inner.get("hostname") or inner.get("name") or f"QNAP {addr}"),
        source="QNAP",
        host=addr,
        model=str(inner.get("model") or inner.get("modelName") or "") or None,
        protocols=["QNAP UDP/7777"],
    )


def _parse_asustor(data: bytes, addr: str) -> NasDevice | None:
    text = data.decode("utf-8", errors="replace")
    blob = text.lower()
    if not any(hint in blob for hint in ("asustor", "adm", "asustek", "lockerstor", "as6")):
        if b"ASUSTOR" not in data and b"ADM" not in data:
            return None
    name = None
    model = None
    version = None
    serial = None
    host = addr
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            name = payload.get("hostname") or payload.get("name") or payload.get("hostName")
            model = payload.get("model") or payload.get("modelName")
            version = payload.get("version") or payload.get("firmware")
            serial = payload.get("serial") or payload.get("serialNumber")
            host = str(payload.get("ip") or payload.get("ipAddress") or addr)
    except json.JSONDecodeError:
        pass
    if not name and not model:
        model_match = re.search(r"(AS\d{4}[A-Z0-9\-]*)", text, re.IGNORECASE)
        if model_match:
            model = model_match.group(1)
    return NasDevice(
        name=str(name or model or f"ASUSTOR {addr}"),
        source="ASUSTOR",
        host=host,
        model=str(model) if model else None,
        version=str(version) if version else None,
        serial=str(serial) if serial else None,
        protocols=["ASUSTOR UDP/8888-8889"],
    )


def _parse_readynas(data: bytes, addr: str) -> NasDevice | None:
    text = data.decode("ascii", errors="replace")
    if "model!!" not in text and "readynas" not in text.lower():
        return None
    hostname_match = re.search(r"\t(\S+)", text)
    ip_match = re.search(r"\t(\d+\.\d+\.\d+\.\d+)\t", text)
    model_match = re.search(r"model!!0!!([^\\n\\t]*)", text)
    serial_match = re.search(r"sn=([^:&\\s]+)", text)
    fw_match = re.search(r"fw=([^:&\\s]+)", text)
    return NasDevice(
        name=hostname_match.group(1) if hostname_match else f"ReadyNAS {addr}",
        source="Netgear ReadyNAS",
        host=ip_match.group(1) if ip_match else addr,
        model=model_match.group(1) if model_match else None,
        version=fw_match.group(1) if fw_match else None,
        serial=serial_match.group(1) if serial_match else None,
        protocols=["RAIDar UDP/22081"],
    )


def _parse_wsd_probe_match(payload: str, source_host: str) -> NasDevice | None:
    if "ProbeMatches" not in payload and "ProbeMatch" not in payload:
        return None
    scopes: list[str] = []
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None

    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "Scopes" and elem.text:
            scopes.extend(part.strip() for part in elem.text.split() if part.strip())

    blob = " ".join(scopes).lower()
    if not any(hint in blob for hint in _NAS_MDNS_HINTS):
        if not any(hint in payload.lower() for hint in ("nas", "storage", "readynas", "terramaster", "tnas")):
            return None

    model = None
    for scope in scopes:
        if "/name/" in scope:
            model = scope.rsplit("/", 1)[-1]
            break

    return NasDevice(
        name=model or f"NAS {source_host}",
        source="WS-Discovery",
        host=source_host,
        model=model,
        protocols=["WS-Discovery UDP/3702"],
    )


def _probe_synology(interface: str, *, timeout_seconds: float) -> list[NasDevice]:
    request = json.dumps({"version": 1, "cmd": "getServerInfo"}).encode("utf-8")
    return _udp_broadcast_collect(
        interface,
        _SYNOLOGY_PORT,
        request,
        timeout_seconds=timeout_seconds,
        parse=_parse_synology,
    )


def _probe_qnap(interface: str, *, timeout_seconds: float) -> list[NasDevice]:
    request = json.dumps({"data": {"type": "discover", "data": {}}}).encode("utf-8")
    return _udp_broadcast_collect(
        interface,
        _QNAP_PORT,
        request,
        timeout_seconds=timeout_seconds,
        parse=_parse_qnap,
    )


def _probe_asustor(interface: str, *, timeout_seconds: float) -> list[NasDevice]:
    found: dict[str, NasDevice] = {}
    for port in _ASUSTOR_PORTS:
        for device in _udp_broadcast_collect(
            interface,
            port,
            _ASUSTOR_PROBES,
            timeout_seconds=timeout_seconds,
            parse=_parse_asustor,
        ):
            key = f"{device.host}|{device.serial or device.name}"
            found[key] = device
    return list(found.values())


def _probe_readynas(interface: str, *, timeout_seconds: float) -> list[NasDevice]:
    return _udp_broadcast_collect(
        interface,
        _READYNAS_PORT,
        _READYNAS_PROBE,
        timeout_seconds=timeout_seconds,
        parse=_parse_readynas,
    )


def _probe_wsd_storage(interface: str, *, timeout_seconds: float) -> list[NasDevice]:
    devices: list[NasDevice] = []
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
        sock.sendto(_WSD_PROBE, _WSD_ADDR)

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            device = _parse_wsd_probe_match(text, addr[0])
            if device is None:
                continue
            key = f"{device.host}|{device.name}"
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
    except OSError as exc:
        logger.debug("WS-Discovery NAS probe failed: %s", exc)
    finally:
        if sock is not None:
            sock.close()
    return devices


def _nas_from_mdns(service) -> NasDevice | None:
    blob = f"{service.name} {service.service_type} {service.host}".lower()
    if not any(hint in blob for hint in _NAS_MDNS_HINTS):
        if not any(token in (service.service_type or "").lower() for token in ("_smb._tcp", "_afpovertcp._tcp")):
            return None
    source = "mDNS"
    if "asustor" in blob:
        source = "ASUSTOR/mDNS"
    elif "synology" in blob or "diskstation" in blob:
        source = "Synology/mDNS"
    elif "qnap" in blob:
        source = "QNAP/mDNS"
    elif "terramaster" in blob or "tnas" in blob:
        source = "TerraMaster/mDNS"
    elif "mycloud" in blob or "wd" in blob:
        source = "WD/mDNS"
    return NasDevice(
        name=service.name or service.service_type,
        source=source,
        host=service.host,
        model=service.txt.get("model"),
        protocols=["mDNS"],
    )


def _nas_from_ssdp(device) -> NasDevice | None:
    blob = " ".join(part for part in (device.usn, device.st, device.server) if part).lower()
    if not any(hint in blob for hint in _NAS_SSDP_HINTS):
        return None
    source = "SSDP"
    if "synology" in blob:
        source = "Synology/SSDP"
    elif "qnap" in blob:
        source = "QNAP/SSDP"
    elif "readynas" in blob or "netgear" in blob:
        source = "ReadyNAS/SSDP"
    elif "asustor" in blob:
        source = "ASUSTOR/SSDP"
    elif "terramaster" in blob:
        source = "TerraMaster/SSDP"
    elif "mycloud" in blob or "western digital" in blob:
        source = "WD/SSDP"
    return NasDevice(
        name=device.usn or device.st or f"NAS {device.host}",
        source=source,
        host=device.host,
        protocols=["SSDP/UPnP"],
    )


def discover_nas_devices(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[NasDevice]:
    found: dict[str, NasDevice] = {}

    collectors = (
        _probe_synology,
        _probe_qnap,
        _probe_asustor,
        _probe_readynas,
        _probe_wsd_storage,
    )
    for collector in collectors:
        for device in collector(interface, timeout_seconds=timeout_seconds):
            key = f"{device.source}|{device.host}|{device.serial or device.name}"
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
        "protocols": [
            "Synology UDP/9997",
            "QNAP UDP/7777",
            "ASUSTOR UDP/8888-8889",
            "Netgear RAIDar UDP/22081",
            "WS-Discovery UDP/3702",
            "mDNS",
            "SSDP/UPnP",
        ],
        "devices": [device.to_dict() for device in devices],
        "note": (
            "Protocolli proprietari Synology/QNAP/ASUSTOR/ReadyNAS più WS-Discovery, "
            "mDNS e SSDP per TerraMaster, WD My Cloud e altri NAS."
        ),
    }
