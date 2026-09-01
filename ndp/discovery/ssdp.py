"""SSDP/UPnP discovery via M-SEARCH."""

from __future__ import annotations

import logging
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_SSDP_ADDR = "239.255.255.250"
_SSDP_PORT = 1900
_DEFAULT_TIMEOUT = 2.0

_HEADER_RE = re.compile(r"^([A-Za-z0-9\-]+):\s*(.*)$", re.MULTILINE)


@dataclass
class SsdpDevice:
    usn: str
    st: str | None = None
    location: str | None = None
    server: str | None = None
    host: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_ssdp_response(payload: str, source_host: str) -> SsdpDevice | None:
    if not payload.startswith("HTTP/"):
        return None
    headers: dict[str, str] = {}
    for match in _HEADER_RE.finditer(payload):
        headers[match.group(1).lower()] = match.group(2).strip()

    usn = headers.get("usn")
    if not usn:
        return None

    return SsdpDevice(
        usn=usn,
        st=headers.get("st") or headers.get("nt"),
        location=headers.get("location"),
        server=headers.get("server"),
        host=source_host,
    )


def discover_ssdp_devices(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[SsdpDevice]:
    devices: list[SsdpDevice] = []
    message = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {_SSDP_ADDR}:{_SSDP_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        f"MX: {max(1, int(timeout_seconds))}\r\n"
        "ST: ssdp:all\r\n"
        "\r\n"
    ).encode("ascii")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(timeout_seconds)
        sock.sendto(message, (_SSDP_ADDR, _SSDP_PORT))

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        seen: set[str] = set()
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            device = _parse_ssdp_response(text, addr[0])
            if device is None or device.usn in seen:
                continue
            seen.add(device.usn)
            devices.append(device)
    except OSError as exc:
        logger.warning("SSDP discovery failed on %s: %s", interface, exc)
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return devices


def discover_ssdp_snapshot(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    devices = discover_ssdp_devices(interface, timeout_seconds=timeout_seconds)
    return {
        "interface": interface,
        "protocol": "SSDP",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "device_count": len(devices),
        "devices": [device.to_dict() for device in devices],
    }
