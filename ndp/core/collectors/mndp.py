"""MikroTik Neighbor Discovery Protocol (MNDP) passive collector."""

from __future__ import annotations

import logging
import socket
import struct
from datetime import datetime, timezone

from ndp.core.state import NeighborState

logger = logging.getLogger(__name__)

MNDP_PORT = 5678
_DEFAULT_LISTEN_SECONDS = 1.5


def _format_mac(raw: bytes) -> str:
    return ":".join(f"{byte:02x}" for byte in raw)


def _format_ipv4(raw: bytes) -> str:
    return ".".join(str(byte) for byte in raw)


def parse_mndp_payload(payload: bytes) -> dict[str, object]:
    """Parse MNDP UDP payload TLV stream."""
    fields: dict[str, object] = {}
    offset = 4  # skip 2-byte header + 2-byte sequence

    while offset + 4 <= len(payload):
        tlv_type, tlv_len = struct.unpack_from("!HH", payload, offset)
        offset += 4
        if offset + tlv_len > len(payload):
            break
        value = payload[offset : offset + tlv_len]
        offset += tlv_len

        if tlv_type == 1 and tlv_len == 6:
            fields["mac"] = _format_mac(value)
        elif tlv_type == 5:
            fields["identity"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 7:
            fields["version"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 8:
            fields["platform"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 10 and tlv_len == 4:
            fields["uptime_seconds"] = struct.unpack("<I", value)[0]
        elif tlv_type == 11:
            fields["software_id"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 12:
            fields["board"] = value.decode("utf-8", errors="replace")
        elif tlv_type in {13, 16}:
            fields["interface"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 17 and tlv_len == 4:
            fields["ipv4"] = _format_ipv4(value)

    return fields


def _fields_to_neighbor(fields: dict[str, object]) -> NeighborState:
    identity = fields.get("identity")
    board = fields.get("board")
    platform = fields.get("platform")
    switch_name = str(identity or board or platform or "MikroTik")
    port_id = fields.get("interface")
    chassis_id = fields.get("mac")
    version = fields.get("version")
    ipv4 = fields.get("ipv4")
    uptime = fields.get("uptime_seconds")
    software_id = fields.get("software_id")

    description_parts = [part for part in (platform, board, version) if part]
    if software_id:
        description_parts.append(f"id={software_id}")
    if uptime is not None:
        description_parts.append(f"uptime={uptime}s")

    return NeighborState(
        protocol="MNDP",
        switch_name=switch_name,
        port_id=str(port_id) if port_id else None,
        chassis_id=str(chassis_id) if chassis_id else None,
        system_description=", ".join(str(part) for part in description_parts) or None,
        software_version=str(version) if version else None,
        platform=str(platform) if platform else None,
        board=str(board) if board else None,
        identity=str(identity) if identity else None,
        ipv4_address=str(ipv4) if ipv4 else None,
        age_seconds=int(uptime) if isinstance(uptime, int) else None,
        last_seen=datetime.now(timezone.utc),
        available=True,
        message="ok",
    )


def collect_mndp_neighbor(
    interface: str,
    *,
    listen_seconds: float = _DEFAULT_LISTEN_SECONDS,
) -> NeighborState:
    """Listen briefly for MNDP announcements on the probe interface."""
    best: NeighborState | None = None
    deadline = datetime.now(timezone.utc).timestamp() + listen_seconds

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            logger.debug("SO_BINDTODEVICE unavailable for MNDP on %s", interface)
        sock.bind(("", MNDP_PORT))
        sock.settimeout(0.25)
    except OSError as exc:
        logger.debug("MNDP listen unavailable on %s: %s", interface, exc)
        return NeighborState(protocol="MNDP", available=False, message="mndp listen unavailable")

    try:
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, _addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                logger.debug("MNDP recv error: %s", exc)
                break

            if len(data) < 8:
                continue

            fields = parse_mndp_payload(data)
            if not fields:
                continue

            neighbor = _fields_to_neighbor(fields)
            if neighbor.available:
                best = neighbor
                break
    finally:
        sock.close()

    if best is not None:
        return best

    return NeighborState(protocol="MNDP", available=False, message="no mndp neighbor")
