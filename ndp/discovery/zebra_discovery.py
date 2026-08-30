"""Zebra Link-OS printer discovery on UDP/4201."""

from __future__ import annotations

import logging
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ZEBRA_PORT = 4201
_DEFAULT_TIMEOUT = 2.5
_ZEBRA_PROBE = b"\x2e\x2c\x3a\x01\x00\x00"
_RESPONSE_MAGIC = b":,."
_HOSTNAME_HINT = re.compile(rb"ZBR[\w-]{3,}")


@dataclass
class ZebraDevice:
    host: str
    product: str | None = None
    hostname: str | None = None
    manufacturer: str = "Zebra"

    def to_printer_fields(self) -> dict[str, Any]:
        name = self.hostname or self.product or f"Zebra {self.host}"
        return {
            "name": name,
            "vendor": "Zebra",
            "category": "industrial",
            "source": "Zebra Link-OS",
            "host": self.host,
            "model": self.product,
            "hostname": self.hostname,
            "protocols": ["Zebra-Discovery/UDP-4201"],
        }


def _ipv4_from_bytes(raw: bytes) -> str | None:
    if len(raw) != 4 or raw in {b"\x00\x00\x00\x00", b"\xff\xff\xff\xff"}:
        return None
    first = raw[0]
    if first == 0 or first >= 224:
        return None
    if not (first == 10 or first == 172 or first == 192 or first == 169):
        return None
    return ".".join(str(byte) for byte in raw)


def _first_null_string(data: bytes, start: int) -> str | None:
    if start >= len(data):
        return None
    end = data.find(b"\x00", start)
    if end <= start:
        return None
    text = data[start:end].decode("ascii", errors="replace").strip()
    if len(text) < 2 or not text.isprintable():
        return None
    return text


def parse_zebra_discovery_response(data: bytes, source_host: str) -> ZebraDevice | None:
    if len(data) < 8 or not data.startswith(_RESPONSE_MAGIC):
        return None

    offset = 4
    if len(data) > offset and data[offset] == 0x03:
        offset += 1

    product = _first_null_string(data, offset)
    hostname_match = _HOSTNAME_HINT.search(data)
    hostname = hostname_match.group(0).decode("ascii", errors="replace") if hostname_match else None

    host = source_host
    for ip_offset in (24, 28, 32):
        if len(data) >= ip_offset + 4:
            candidate = _ipv4_from_bytes(data[ip_offset : ip_offset + 4])
            if candidate:
                host = candidate
                break

    if not any([product, hostname]):
        return None

    return ZebraDevice(host=host, product=product, hostname=hostname)


def discover_zebra_printers(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[ZebraDevice]:
    devices: dict[str, ZebraDevice] = {}
    sock: socket.socket | None = None

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(0.35)

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        next_probe = 0.0
        while datetime.now(timezone.utc).timestamp() < deadline:
            now = datetime.now(timezone.utc).timestamp()
            if now >= next_probe:
                for _ in range(3):
                    try:
                        sock.sendto(_ZEBRA_PROBE, ("255.255.255.255", _ZEBRA_PORT))
                    except OSError as exc:
                        logger.debug("Zebra discovery probe failed: %s", exc)
                next_probe = now + 1.0

            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue

            device = parse_zebra_discovery_response(data, addr[0])
            if device is None:
                continue
            key = device.hostname or device.product or device.host
            devices[key] = device
    except OSError as exc:
        logger.warning("Zebra discovery failed on %s: %s", interface, exc)
    finally:
        if sock is not None:
            sock.close()

    return list(devices.values())
