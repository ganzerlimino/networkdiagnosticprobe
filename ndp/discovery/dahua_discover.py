"""Dahua DHDiscover UDP discovery (port 37810)."""

from __future__ import annotations

import json
import logging
import socket
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DAHUA_PORT = 37810
_DEFAULT_TIMEOUT = 2.5
_PROBE_BODY = b'{"method":"DHDiscover.search","params":{"mac":"","uni":1}}'


@dataclass
class DahuaDevice:
    host: str
    mac: str | None = None
    model: str | None = None
    serial: str | None = None
    manufacturer: str | None = None
    http_port: int | None = None
    firmware: str | None = None

    def to_camera_fields(self) -> dict[str, Any]:
        name = self.model or f"Dahua {self.host}"
        return {
            "name": name,
            "source": "Dahua DHDiscover",
            "host": self.host,
            "port": self.http_port,
            "manufacturer": self.manufacturer or "Dahua",
            "model": self.model,
            "protocols": ["DHDiscover/UDP-37810"],
        }


def build_dahua_probe() -> bytes:
    packet = bytearray(32 + len(_PROBE_BODY))
    packet[0] = 0xA3
    struct.pack_into("<I", packet, 4, len(_PROBE_BODY))
    packet[32:] = _PROBE_BODY
    return bytes(packet)


def _parse_dahua_json(payload: dict[str, Any], source_host: str) -> DahuaDevice | None:
    params = payload.get("params")
    if not isinstance(params, dict):
        return None

    device_info = params.get("deviceInfo")
    if not isinstance(device_info, dict):
        device_info = params

    if payload.get("method") == "DHDiscover.search":
        return None

    ipv4 = device_info.get("IPv4Address")
    host = source_host
    if isinstance(ipv4, dict):
        host = str(ipv4.get("IPAddress") or source_host)

    http_port = device_info.get("HttpPort")
    return DahuaDevice(
        host=host,
        mac=str(device_info.get("MAC") or device_info.get("Mac") or "") or None,
        model=str(device_info.get("DeviceType") or device_info.get("MachineName") or "") or None,
        serial=str(device_info.get("SerialNo") or device_info.get("SerialNumber") or "") or None,
        manufacturer=str(device_info.get("Vendor") or device_info.get("Manufacturer") or "") or None,
        http_port=int(http_port) if isinstance(http_port, int) else None,
        firmware=str(device_info.get("Version") or "") or None,
    )


def parse_dahua_response(data: bytes, source_host: str) -> DahuaDevice | None:
    if len(data) < 32 or data[0] not in (0xB3, 0xA3):
        return None
    body_len = struct.unpack_from("<I", data, 4)[0]
    if body_len <= 0 or 32 + body_len > len(data):
        return None
    body = data[32 : 32 + body_len]
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return _parse_dahua_json(payload, source_host)


def discover_dahua_cameras(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[DahuaDevice]:
    devices: list[DahuaDevice] = []
    seen: set[str] = set()
    sock: socket.socket | None = None
    probe = build_dahua_probe()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(timeout_seconds)
        sock.sendto(probe, ("255.255.255.255", _DAHUA_PORT))

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            device = parse_dahua_response(data, addr[0])
            if device is None:
                continue
            key = device.serial or device.mac or device.host
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
    except OSError as exc:
        logger.warning("Dahua DHDiscover failed on %s: %s", interface, exc)
    finally:
        if sock is not None:
            sock.close()

    return devices
