"""Weintek HMI Search discovery (Utility Manager / EasyBuilder)."""

from __future__ import annotations

import logging
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ndp.discovery.oui import lookup_vendor
from ndp.scan.ports import probe_tcp_port

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 2.5

# HMI Search tool (UDP 59999 request / 60000 response) plus documented fallbacks.
_HMI_SEARCH_SEND_PORT = 59999
_HMI_SEARCH_RECV_PORT = 60000
_UDP_PORTS = (_HMI_SEARCH_SEND_PORT, _HMI_SEARCH_RECV_PORT, 10275, 20249)
_TCP_SEARCH_PORT = 10275

_MANAGEMENT_PORTS: tuple[tuple[int, str], ...] = (
    (8000, "HMI / EasyAccess"),
    (8001, "EasyDiagnoser / cMT upload"),
    (5900, "VNC"),
)

_PROBES: tuple[bytes, ...] = (
    b"",
    b"SEARCH",
    b"search",
    b"HMI",
    b"HMI SEARCH",
    b"FIND",
    b"WEINTEK",
    b"\x57\x45\x49\x4e\x54\x45\x4b\x00",
)

_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_MAC_RE = re.compile(r"\b([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})\b")
_MODEL_RE = re.compile(
    r"\b(cMT[\w\-]+|MT[\d]{3,4}[\w\-]*|eMT[\w\-]+|mTV[\w\-]+|MTip[\w\-]+)\b",
    re.IGNORECASE,
)
_FW_RE = re.compile(
    r"(?:firmware|version|fw|os)[\s:=]+([^\s,;|]+)",
    re.IGNORECASE,
)


@dataclass
class WeintekHmiDevice:
    name: str
    host: str
    mac: str | None = None
    subnet_mask: str | None = None
    firmware: str | None = None
    vendor: str | None = None
    source: str = "Weintek HMI Search"
    discovery_port: int | None = None
    open_ports: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_mac(mac: str) -> str:
    cleaned = mac.replace("-", ":").upper()
    parts = cleaned.split(":")
    if len(parts) == 6:
        return ":".join(part.zfill(2) for part in parts)
    return cleaned.upper()


def _looks_like_weintek(text: str) -> bool:
    lower = text.lower()
    if _MODEL_RE.search(text):
        return True
    hints = (
        "weintek",
        "easybuilder",
        "easyaccess",
        "cmt-",
        "mt807",
        "mt810",
        "emt",
        "mtip",
    )
    return any(hint in lower for hint in hints)


def parse_weintek_response(data: bytes, source_host: str, *, port: int | None = None) -> WeintekHmiDevice | None:
    text = data.decode("utf-8", errors="replace").strip("\x00\r\n\t ")
    if len(text) < 3:
        return None
    if not _looks_like_weintek(text) and not _IP_RE.search(text):
        return None

    ips = _IP_RE.findall(text)
    host = ips[0] if ips else source_host
    subnet = ips[1] if len(ips) > 1 and _is_netmask(ips[1]) else None
    if len(ips) > 1 and not subnet:
        for candidate in ips[1:]:
            if _is_netmask(candidate):
                subnet = candidate
                break

    mac_match = _MAC_RE.search(text)
    mac = _normalize_mac(mac_match.group(1)) if mac_match else None

    model_match = _MODEL_RE.search(text)
    name = model_match.group(1) if model_match else f"Weintek {host}"

    firmware = None
    fw_match = _FW_RE.search(text)
    if fw_match:
        firmware = fw_match.group(1).strip()
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or _IP_RE.fullmatch(line) or _MAC_RE.search(line):
                continue
            if _MODEL_RE.search(line):
                continue
            if re.match(r"^[Vv]?\d+(\.\d+)+", line):
                firmware = line
                break

    vendor = lookup_vendor(mac) if mac else None
    return WeintekHmiDevice(
        name=name,
        host=host,
        mac=mac,
        subnet_mask=subnet,
        firmware=firmware,
        vendor=vendor,
        discovery_port=port,
    )


def _is_netmask(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        return False
    if any(octet < 0 or octet > 255 for octet in octets):
        return False
    binary = "".join(f"{octet:08b}" for octet in octets)
    return "01" not in binary or binary == "0" * 32


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


def _udp_listen_collect(
    interface: str,
    listen_port: int,
    send_port: int,
    *,
    timeout_seconds: float,
) -> list[WeintekHmiDevice]:
    devices: list[WeintekHmiDevice] = []
    seen: set[str] = set()
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        try:
            sock.bind(("", listen_port))
        except OSError:
            sock.bind(("", 0))
            listen_port = sock.getsockname()[1]

        sock.settimeout(0.35)
        for probe in _PROBES:
            try:
                sock.sendto(probe, ("255.255.255.255", send_port))
            except OSError:
                continue

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            remaining = deadline - datetime.now(timezone.utc).timestamp()
            if remaining <= 0:
                break
            sock.settimeout(min(0.4, remaining))
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            device = parse_weintek_response(data, addr[0], port=listen_port)
            if device is None:
                continue
            key = device.mac or device.host
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
    except OSError as exc:
        logger.debug("Weintek UDP discovery failed on %s:%s: %s", listen_port, send_port, exc)
    finally:
        if sock is not None:
            sock.close()
    return devices


def _udp_broadcast_collect(interface: str, port: int, *, timeout_seconds: float) -> list[WeintekHmiDevice]:
    devices: list[WeintekHmiDevice] = []
    seen: set[str] = set()
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(timeout_seconds)
        for probe in _PROBES:
            try:
                sock.sendto(probe, ("255.255.255.255", port))
            except OSError:
                continue

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            device = parse_weintek_response(data, addr[0], port=port)
            if device is None:
                continue
            key = device.mac or device.host
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
    except OSError as exc:
        logger.debug("Weintek UDP broadcast on port %s failed: %s", port, exc)
    finally:
        if sock is not None:
            sock.close()
    return devices


def _tcp_search_collect(interface: str, *, timeout_seconds: float) -> list[WeintekHmiDevice]:
    devices: list[WeintekHmiDevice] = []
    seen: set[str] = set()
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.settimeout(0.2)
        sock.sendto(b"SEARCH", ("255.255.255.255", _TCP_SEARCH_PORT))
    except OSError:
        pass
    finally:
        if sock is not None:
            sock.close()

    # TCP search: try broadcast subnet via limited connect sweep is expensive;
    # rely on UDP paths and return empty for TCP-only sweep without target list.
    _ = interface, timeout_seconds, devices, seen
    return []


def discover_weintek_hmi(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
    probe_ports: bool = True,
    port_timeout_seconds: float = 0.8,
) -> list[WeintekHmiDevice]:
    found: dict[str, WeintekHmiDevice] = {}

    for device in _udp_listen_collect(
        interface,
        _HMI_SEARCH_RECV_PORT,
        _HMI_SEARCH_SEND_PORT,
        timeout_seconds=timeout_seconds,
    ):
        key = device.mac or device.host
        found[key] = device

    for port in _UDP_PORTS:
        if port in (_HMI_SEARCH_SEND_PORT, _HMI_SEARCH_RECV_PORT):
            continue
        for device in _udp_broadcast_collect(interface, port, timeout_seconds=timeout_seconds / 2):
            key = device.mac or device.host
            found.setdefault(key, device)

    for device in _tcp_search_collect(interface, timeout_seconds=timeout_seconds / 3):
        key = device.mac or device.host
        found.setdefault(key, device)

    devices = list(found.values())
    if probe_ports:
        for device in devices:
            device.open_ports = _probe_management_ports(device.host, timeout_seconds=port_timeout_seconds)
    devices.sort(key=lambda item: item.host)
    return devices
