"""Epson Network Peripheral Control (ENPC) discovery on UDP/3289."""

from __future__ import annotations

import logging
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ndp.discovery.host import normalize_mac

logger = logging.getLogger(__name__)

_ENPC_PORT = 3289
_DEFAULT_TIMEOUT = 2.5
_EPSON_PROBES = (
    b"EPSONP" + b"\x00" * 8,
    b"EPSONQ" + bytes([0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    b"EPSONQ" + bytes([0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00]),
)
_MODEL_HINT = re.compile(rb"(TM-[A-Za-z0-9-]+|FP-[A-Za-z0-9-]+|EU-[A-Za-z0-9-]+)")


@dataclass
class EnpcDevice:
    host: str
    mac: str | None = None
    model: str | None = None
    manufacturer: str = "Epson"

    def to_printer_fields(self) -> dict[str, Any]:
        name = self.model or f"Epson {self.host}"
        return {
            "name": name,
            "vendor": "Epson",
            "category": "retail",
            "source": "Epson ENPC",
            "host": self.host,
            "mac": self.mac,
            "model": self.model,
            "protocols": ["ENPC/UDP-3289"],
        }


def _ipv4_from_bytes(raw: bytes) -> str | None:
    if len(raw) != 4 or raw == b"\x00\x00\x00\x00" or raw == b"\xff\xff\xff\xff":
        return None
    if raw[0] == 0:
        return None
    return ".".join(str(byte) for byte in raw)


def _mac_from_bytes(raw: bytes) -> str | None:
    if len(raw) != 6 or raw == b"\x00" * 6 or raw == b"\xff" * 6:
        return None
    return normalize_mac(":".join(f"{byte:02x}" for byte in raw))


def _extract_model(data: bytes) -> str | None:
    match = _MODEL_HINT.search(data)
    if match:
        return match.group(1).decode("ascii", errors="replace")

    for start in (13, 14, 20):
        if start >= len(data):
            continue
        chunk = data[start : start + 64]
        if b"\x00" not in chunk:
            continue
        text = chunk.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        if len(text) >= 3 and text.isprintable() and not text.startswith("EPSON"):
            return text
    return None


def parse_enpc_response(data: bytes, source_host: str) -> EnpcDevice | None:
    if len(data) < 13 or not data.startswith(b"EPSON"):
        return None

    host = _ipv4_from_bytes(data[24:28]) if len(data) >= 28 else None
    mac = _mac_from_bytes(data[16:22]) if len(data) >= 22 else None
    model = _extract_model(data)

    if not any([host, mac, model]):
        return None

    return EnpcDevice(
        host=host or source_host,
        mac=mac,
        model=model,
    )


def discover_epson_enpc(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[EnpcDevice]:
    devices: dict[str, EnpcDevice] = {}
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

        for probe in _EPSON_PROBES:
            try:
                sock.sendto(probe, ("255.255.255.255", _ENPC_PORT))
            except OSError as exc:
                logger.debug("ENPC probe send failed: %s", exc)

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            device = parse_enpc_response(data, addr[0])
            if device is None:
                continue
            key = device.mac or f"{device.host}|{device.model or ''}"
            devices[key] = device
    except OSError as exc:
        logger.warning("Epson ENPC discovery failed on %s: %s", interface, exc)
    finally:
        if sock is not None:
            sock.close()

    return list(devices.values())
