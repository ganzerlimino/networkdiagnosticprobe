"""Passive DHCP Option 82 (Relay Agent Information) detection."""

from __future__ import annotations

import logging
import socket
import struct
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DHCP_SERVER_PORT = 67
_DHCP_CLIENT_PORT = 68
_OPTION_RELAY_AGENT = 82
_MAGIC_COOKIE = b"\x63\x82\x53\x63"


@dataclass
class DhcpOption82Sample:
    source_ip: str
    message_type: str
    circuit_id: str | None = None
    remote_id: str | None = None
    raw_hex: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DhcpOption82Snapshot:
    interface: str
    listen_seconds: float
    scanned_at: datetime
    available: bool
    message: str
    samples: list[DhcpOption82Sample] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interface": self.interface,
            "listen_seconds": self.listen_seconds,
            "scanned_at": self.scanned_at.isoformat(),
            "available": self.available,
            "message": self.message,
            "sample_count": len(self.samples),
            "samples": [sample.to_dict() for sample in self.samples],
        }


def _decode_text(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip() or value.hex()


def _parse_option82(data: bytes) -> tuple[str | None, str | None]:
    circuit_id: str | None = None
    remote_id: str | None = None
    offset = 0
    while offset + 2 <= len(data):
        sub_type = data[offset]
        sub_len = data[offset + 1]
        offset += 2
        if offset + sub_len > len(data):
            break
        value = data[offset : offset + sub_len]
        offset += sub_len
        if sub_type == 1:
            circuit_id = _decode_text(value)
        elif sub_type == 2:
            remote_id = _decode_text(value)
    return circuit_id, remote_id


def _parse_dhcp_options(payload: bytes) -> dict[int, bytes]:
    options: dict[int, bytes] = {}
    if _MAGIC_COOKIE not in payload:
        return options
    offset = payload.index(_MAGIC_COOKIE) + 4
    while offset < len(payload):
        opt = payload[offset]
        offset += 1
        if opt == 255:
            break
        if opt == 0:
            continue
        if offset >= len(payload):
            break
        length = payload[offset]
        offset += 1
        if offset + length > len(payload):
            break
        options[opt] = payload[offset : offset + length]
        offset += length
    return options


def _dhcp_message_name(msg_type: int | None) -> str:
    return {
        1: "DISCOVER",
        2: "OFFER",
        3: "REQUEST",
        4: "DECLINE",
        5: "ACK",
        6: "NAK",
        7: "RELEASE",
        8: "INFORM",
    }.get(msg_type or 0, "UNKNOWN")


def _parse_dhcp_packet(packet: bytes, source_ip: str) -> DhcpOption82Sample | None:
    if len(packet) < 240:
        return None
    options = _parse_dhcp_options(packet)
    if _OPTION_RELAY_AGENT not in options:
        return None

    option82 = options[_OPTION_RELAY_AGENT]
    circuit_id, remote_id = _parse_option82(option82)
    msg_type = None
    if 53 in options and options[53]:
        msg_type = options[53][0]

    return DhcpOption82Sample(
        source_ip=source_ip,
        message_type=_dhcp_message_name(msg_type),
        circuit_id=circuit_id,
        remote_id=remote_id,
        raw_hex=option82.hex(),
    )


def _extract_udp_payload(frame: bytes) -> tuple[int, int, bytes] | None:
    if len(frame) < 14:
        return None

    offset = 12
    field_type = struct.unpack("!H", frame[offset : offset + 2])[0]
    if field_type in (0x8100, 0x88A8, 0x9100):
        offset += 4
        if offset + 2 > len(frame):
            return None
        field_type = struct.unpack("!H", frame[offset : offset + 2])[0]
    if field_type != 0x0800 or offset + 20 > len(frame):
        return None

    ip_start = offset
    ihl = (frame[ip_start] & 0x0F) * 4
    if frame[ip_start + 9] != 17:
        return None
    ip_header_end = ip_start + ihl
    if ip_header_end + 8 > len(frame):
        return None

    src_ip = ".".join(str(byte) for byte in frame[ip_start + 12 : ip_start + 16])
    udp_start = ip_header_end
    src_port, dst_port = struct.unpack("!HH", frame[udp_start : udp_start + 4])
    if {src_port, dst_port}.isdisjoint({_DHCP_SERVER_PORT, _DHCP_CLIENT_PORT}):
        return None

    udp_len = struct.unpack("!H", frame[udp_start + 4 : udp_start + 6])[0]
    payload_start = udp_start + 8
    payload_end = min(len(frame), payload_start + max(0, udp_len - 8))
    return src_port, dst_port, frame[payload_start:payload_end]


def sniff_dhcp_option82(
    interface: str,
    *,
    listen_seconds: float = 3.0,
) -> DhcpOption82Snapshot:
    scanned_at = datetime.now(timezone.utc)
    samples: list[DhcpOption82Sample] = []
    seen: set[str] = set()

    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
        sock.bind((interface, 0))
        sock.settimeout(0.25)
    except OSError as exc:
        logger.warning("DHCP Option 82 sniff unavailable on %s: %s", interface, exc)
        return DhcpOption82Snapshot(
            interface=interface,
            listen_seconds=listen_seconds,
            scanned_at=scanned_at,
            available=False,
            message=f"sniff non disponibile: {exc}",
        )

    deadline = scanned_at.timestamp() + listen_seconds
    try:
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                frame = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            extracted = _extract_udp_payload(frame)
            if extracted is None:
                continue
            _src_port, _dst_port, payload = extracted
            if len(payload) < 240:
                continue

            src_ip = "0.0.0.0"
            if len(frame) >= 34:
                ip_start = 14
                if struct.unpack("!H", frame[12:14])[0] in (0x8100, 0x88A8, 0x9100):
                    ip_start = 18
                if struct.unpack("!H", frame[ip_start + 2 : ip_start + 4])[0] == 0x0800:
                    src_ip = ".".join(str(byte) for byte in frame[ip_start + 12 : ip_start + 16])

            sample = _parse_dhcp_packet(payload, src_ip)
            if sample is None:
                continue
            key = f"{sample.message_type}|{sample.circuit_id}|{sample.remote_id}"
            if key in seen:
                continue
            seen.add(key)
            samples.append(sample)
    finally:
        sock.close()

    if samples:
        message = f"Option 82 rilevata in {len(samples)} pacchetto/i DHCP"
    else:
        message = "nessun pacchetto DHCP con Option 82 nel periodo di ascolto"

    return DhcpOption82Snapshot(
        interface=interface,
        listen_seconds=listen_seconds,
        scanned_at=scanned_at,
        available=True,
        message=message,
        samples=samples,
    )
