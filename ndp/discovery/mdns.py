"""mDNS service discovery (passive listen + PTR query)."""

from __future__ import annotations

import logging
import re
import socket
import struct
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_MDNS_ADDR = "224.0.0.251"
_MDNS_PORT = 5353
_DEFAULT_TIMEOUT = 2.0


@dataclass
class MdnsService:
    name: str
    service_type: str
    host: str | None = None
    port: int | None = None
    addresses: list[str] = field(default_factory=list)
    txt: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _decode_name(packet: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    jumped = False
    jump_offset = offset
    while True:
        if offset >= len(packet):
            break
        length = packet[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                break
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if not jumped:
                jump_offset = offset + 2
            offset = pointer
            jumped = True
            continue
        offset += 1
        labels.append(packet[offset : offset + length].decode("utf-8", errors="replace"))
        offset += length
    name = ".".join(labels)
    return name, (jump_offset if jumped else offset)


def _parse_txt_rdata(data: bytes) -> dict[str, str]:
    txt: dict[str, str] = {}
    offset = 0
    while offset < len(data):
        length = data[offset]
        offset += 1
        chunk = data[offset : offset + length].decode("utf-8", errors="replace")
        offset += length
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            txt[key] = value
        elif chunk:
            txt[chunk] = ""
    return txt


def _parse_response(packet: bytes) -> list[MdnsService]:
    services: list[MdnsService] = []
    if len(packet) < 12:
        return services

    question_count = struct.unpack("!H", packet[4:6])[0]
    answer_count = struct.unpack("!H", packet[6:8])[0]
    offset = 12

    for _ in range(question_count):
        _, offset = _decode_name(packet, offset)
        offset += 4

    for _ in range(answer_count):
        name, offset = _decode_name(packet, offset)
        if offset + 10 > len(packet):
            break
        rtype, rclass, _ttl, rdlength = struct.unpack("!HHIH", packet[offset : offset + 10])
        offset += 10
        rdata = packet[offset : offset + rdlength]
        offset += rdlength

        if rtype == 12:  # PTR
            target, _ = _decode_name(rdata, 0)
            service_type = name
            services.append(MdnsService(name=target.rstrip("."), service_type=service_type.rstrip(".")))
        elif rtype == 33 and len(rdata) >= 6:  # SRV
            priority, weight, port = struct.unpack("!HHH", rdata[:6])
            _ = priority + weight
            target, _ = _decode_name(rdata, 6)
            host = target.rstrip(".")
            if services:
                services[-1].host = host
                services[-1].port = port
        elif rtype == 1 and len(rdata) == 4:  # A
            address = ".".join(str(byte) for byte in rdata)
            if services:
                services[-1].addresses.append(address)
        elif rtype == 16:  # TXT
            if services:
                services[-1].txt.update(_parse_txt_rdata(rdata))

    deduped: dict[str, MdnsService] = {}
    for service in services:
        key = f"{service.name}|{service.service_type}"
        if key not in deduped:
            deduped[key] = service
    return list(deduped.values())


def discover_mdns_services(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[MdnsService]:
    services: list[MdnsService] = []
    query = (
        b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
        b"\x09_services\x07_dns-sd\x04_udp\x05local\x00"
        b"\x00\x0c\x00\x01"
    )

    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            pass
        sock.bind(("", _MDNS_PORT))
        sock.settimeout(timeout_seconds)
        mreq = struct.pack("=4s4s", socket.inet_aton(_MDNS_ADDR), socket.inet_aton("0.0.0.0"))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.sendto(query, (_MDNS_ADDR, _MDNS_PORT))

        deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            services.extend(_parse_response(data))
    except OSError as exc:
        logger.warning("mDNS discovery failed on %s: %s", interface, exc)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    return services


def discover_mdns_snapshot(
    interface: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    services = discover_mdns_services(interface, timeout_seconds=timeout_seconds)
    return {
        "interface": interface,
        "protocol": "mDNS",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "service_count": len(services),
        "services": [service.to_dict() for service in services],
    }
