"""eWON (Cosy / Flexy) discovery via IPCONF and HMS MAC OUI hints."""

from __future__ import annotations

import logging
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ndp.discovery.neigh import lookup_neighbor_mac
from ndp.discovery.oui import EWON_OUIS, lookup_vendor
from ndp.scan.ports import probe_tcp_port

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 2.5
_DISCOVERY_PORT = 1507
_RESPONSE_PORT = 1506
_ALT_UDP_PORTS = (1234, 4242)

_DISCOVERY_PACKETS = (
    bytes.fromhex(
        "4950434f4e4600000000000000000000000000000000000000000000000000000000000000000000"
    ),
    bytes.fromhex(
        "4950434f4e460000000000000000000a000000000000000000000000000000000000000000000000"
    ),
)

_MANAGEMENT_PORTS: tuple[tuple[int, str], ...] = (
    (80, "HTTP"),
    (443, "HTTPS"),
    (21, "FTP"),
)

_PRODUCT_CODE_MODELS: dict[int, str] = {
    1: "Cosy",
    2: "Flexy",
    3: "Cosy 131",
    4: "Flexy 205",
    131: "Cosy 131",
    205: "Flexy 205",
}


@dataclass
class EwonDevice:
    host: str
    model: str | None = None
    serial: str | None = None
    mac: str | None = None
    netmask: str | None = None
    firmware: str | None = None
    product_code: str | None = None
    vendor: str | None = "HMS Industrial Networks / eWON"
    source: str = "eWON IPCONF"
    discovery_port: int | None = None
    open_ports: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _format_ip_reversed(data: bytes, start: int) -> str | None:
    if len(data) < start + 4:
        return None
    return f"{data[start + 3]}.{data[start + 2]}.{data[start + 1]}.{data[start]}"


def _format_mac(data: bytes, start: int = 32) -> str | None:
    if len(data) < start + 6:
        return None
    return ":".join(f"{byte:02X}" for byte in data[start : start + 6])


def _parse_serial(data: bytes) -> str | None:
    if len(data) < 20:
        return None
    serial_part1 = data[19]
    raw16 = (data[18] << 8) | data[17] if len(data) >= 19 else 0
    serial_part2 = raw16 // 1000
    serial_part3 = data[17] if len(data) >= 18 else 0
    if raw16 % 1000 >= 500:
        serial_part3 = (serial_part3 + 0x80) & 0xFF
    serial_part4 = data[16] if len(data) >= 17 else 0
    return f"{serial_part1}{serial_part2}-{serial_part3:04}-{serial_part4}"


def parse_ipconf_device_info(data: bytes) -> EwonDevice | None:
    if len(data) < 16 or data[15] != 2:
        return None
    host = _format_ip_reversed(data, 20) or "0.0.0.0"
    netmask = _format_ip_reversed(data, 24)
    mac = _format_mac(data)
    product_code = str(data[16]) if len(data) > 16 else None
    model = _PRODUCT_CODE_MODELS.get(data[16]) if len(data) > 16 else None
    identifier = data[:4].decode("ascii", errors="replace") if len(data) >= 4 else None
    if identifier and identifier != "IPCO":
        return None
    return EwonDevice(
        host=host,
        model=model,
        serial=_parse_serial(data),
        mac=mac,
        netmask=netmask,
        product_code=product_code,
        vendor=lookup_vendor(mac) if mac else "HMS Industrial Networks / eWON",
    )


def parse_ipconf_firmware_info(data: bytes) -> str | None:
    if len(data) < 16 or data[15] != 5:
        return None
    raw = data[20:]
    end = raw.find(b"\x00")
    if end == -1:
        end = len(raw)
    text = raw[:end].decode("utf-8", errors="replace").strip()
    return text or None


def parse_ipconf_response(data: bytes) -> EwonDevice | None:
    if len(data) < 16:
        return None
    if data[15] == 2:
        return parse_ipconf_device_info(data)
    if data[15] == 5:
        firmware = parse_ipconf_firmware_info(data)
        if not firmware:
            return None
        return EwonDevice(host="0.0.0.0", firmware=firmware, source="eWON IPCONF firmware")
    return None


def _merge_devices(partials: list[EwonDevice]) -> list[EwonDevice]:
    merged: dict[str, EwonDevice] = {}

    for item in partials:
        key = item.mac or item.host
        if key not in merged:
            merged[key] = item
            continue
        existing = merged[key]
        merged[key] = EwonDevice(
            host=existing.host,
            model=existing.model or item.model,
            serial=existing.serial or item.serial,
            mac=existing.mac or item.mac,
            netmask=existing.netmask or item.netmask,
            firmware=existing.firmware or item.firmware,
            product_code=existing.product_code or item.product_code,
            vendor=existing.vendor or item.vendor,
            source=existing.source,
            discovery_port=existing.discovery_port or item.discovery_port,
            open_ports=existing.open_ports or item.open_ports,
        )

    return list(merged.values())


def _ipconf_collect(
    interface: str,
    *,
    timeout_seconds: float,
    discovery_port: int = _DISCOVERY_PORT,
) -> list[EwonDevice]:
    partials: list[EwonDevice] = []
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        try:
            sock.bind(("", _RESPONSE_PORT))
        except OSError:
            sock.bind(("", 0))

        sock.settimeout(timeout_seconds)
        for packet in _DISCOVERY_PACKETS:
            try:
                sock.sendto(packet, ("255.255.255.255", discovery_port))
            except OSError:
                continue

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                break
            device = parse_ipconf_response(data)
            if device is None:
                continue
            if device.host == "0.0.0.0":
                device.host = addr[0]
            device.discovery_port = discovery_port
            partials.append(device)
    except OSError as exc:
        logger.debug("eWON IPCONF on port %s failed: %s", discovery_port, exc)
    finally:
        if sock is not None:
            sock.close()

    merged = _merge_devices(partials)
    return merged


def _ewon_from_oui_neighbors(interface: str) -> list[EwonDevice]:
    devices: list[EwonDevice] = []
    try:
        from ndp.core.subprocess_runner import run_command

        output = run_command(["ip", "-4", "neigh", "show", "dev", interface])
    except (OSError, FileNotFoundError):
        return devices

    line_re = re.compile(
        r"^(?P<ip>\d+\.\d+\.\d+\.\d+)\s+lladdr\s+(?P<mac>[0-9a-f:]+)\s+(?P<state>\S+)"
    )
    for line in output.splitlines():
        match = line_re.match(line.strip())
        if not match or match.group("state") in {"FAILED", "INCOMPLETE"}:
            continue
        mac = match.group("mac").upper()
        prefix = ":".join(mac.split(":")[:3])
        if prefix not in EWON_OUIS:
            continue
        ip = match.group("ip")
        devices.append(
            EwonDevice(
                host=ip,
                mac=mac,
                model=None,
                vendor=lookup_vendor(mac),
                source="eWON OUI/neighbor",
            )
        )
    return devices


def _probe_management_ports(host: str, *, timeout_seconds: float) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for port, service in _MANAGEMENT_PORTS:
        is_open, latency = probe_tcp_port(host, port, timeout_seconds)
        entries.append(
            {
                "port": port,
                "service": service,
                "open": is_open,
                "latency_ms": round(latency, 1) if latency is not None else None,
            }
        )
    return entries


def discover_ewon_devices(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
    probe_ports: bool = True,
    port_timeout_seconds: float = 0.8,
) -> list[EwonDevice]:
    found: dict[str, EwonDevice] = {}

    for port in (_DISCOVERY_PORT, *_ALT_UDP_PORTS):
        for device in _ipconf_collect(interface, timeout_seconds=timeout_seconds / 2, discovery_port=port):
            key = device.mac or device.host
            found[key] = device

    for device in _ewon_from_oui_neighbors(interface):
        key = device.mac or device.host
        if key not in found:
            found[key] = device
        else:
            existing = found[key]
            if not existing.mac and device.mac:
                existing.mac = device.mac
            if not existing.vendor and device.vendor:
                existing.vendor = device.vendor

    devices = list(found.values())
    if probe_ports:
        for device in devices:
            device.open_ports = _probe_management_ports(device.host, timeout_seconds=port_timeout_seconds)
            if not device.mac:
                mac = lookup_neighbor_mac(interface, device.host)
                if mac:
                    device.mac = mac.upper()
    devices.sort(key=lambda item: item.host)
    return devices
