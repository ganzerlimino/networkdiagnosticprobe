"""Hikvision SADP (Search Active Devices Protocol) discovery."""

from __future__ import annotations

import logging
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

_SADP_ADDR = ("239.255.255.250", 37020)
_DEFAULT_TIMEOUT = 2.5


@dataclass
class SadpDevice:
    host: str
    mac: str | None = None
    model: str | None = None
    serial: str | None = None
    device_type: str | None = None
    firmware: str | None = None
    http_port: int | None = None
    command_port: int | None = None

    def to_camera_fields(self) -> dict[str, Any]:
        name = self.model or self.device_type or f"Hikvision {self.host}"
        return {
            "name": name,
            "source": "Hikvision SADP",
            "host": self.host,
            "port": self.http_port,
            "manufacturer": "Hikvision",
            "model": self.model or self.device_type,
            "protocols": ["SADP/UDP-37020"],
        }


def _build_probe(probe_type: str = "inquiry") -> bytes:
    probe_uuid = str(uuid.uuid4()).upper()
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f"<Probe><Uuid>{probe_uuid}</Uuid><Types>{probe_type}</Types></Probe>"
    )
    return xml.encode("utf-8")


def _xml_text(root: ElementTree.Element, tag: str) -> str | None:
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] == tag and elem.text:
            return elem.text.strip()
    return None


def parse_sadp_probe_match(payload: str, source_host: str) -> SadpDevice | None:
    if "ProbeMatch" not in payload:
        return None
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None

    host = _xml_text(root, "IPv4Address") or source_host
    mac = _xml_text(root, "MAC")
    if mac:
        mac = mac.replace("-", ":").upper()

    http_port_raw = _xml_text(root, "HttpPort")
    command_port_raw = _xml_text(root, "CommandPort")
    return SadpDevice(
        host=host,
        mac=mac,
        model=_xml_text(root, "DeviceDescription") or _xml_text(root, "DeviceType"),
        serial=_xml_text(root, "DeviceSN"),
        device_type=_xml_text(root, "DeviceType"),
        firmware=_xml_text(root, "SoftwareVersion"),
        http_port=int(http_port_raw) if http_port_raw and http_port_raw.isdigit() else None,
        command_port=int(command_port_raw) if command_port_raw and command_port_raw.isdigit() else None,
    )


def discover_hikvision_sadp(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[SadpDevice]:
    devices: list[SadpDevice] = []
    seen: set[str] = set()
    sock: socket.socket | None = None
    probes = (_build_probe("inquiry"), _build_probe("inquiry_v32"))

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(timeout_seconds)

        for probe in probes:
            sock.sendto(probe, _SADP_ADDR)
            sock.sendto(probe, ("255.255.255.255", _SADP_ADDR[1]))

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            if "DHDiscover.search" in text:
                continue
            device = parse_sadp_probe_match(text, addr[0])
            if device is None:
                continue
            key = device.mac or device.host
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
    except OSError as exc:
        logger.warning("Hikvision SADP discovery failed on %s: %s", interface, exc)
    finally:
        if sock is not None:
            sock.close()

    return devices
