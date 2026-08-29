"""Passive L2 ethertype detection for proprietary discovery frames."""

from __future__ import annotations

import logging
import socket
import struct
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ETHERTYPES = {
    0x2000: "FDP",
    0xEEEE: "EDP",
    0x88D9: "LLTD",
}


@dataclass
class L2ProtocolHit:
    protocol: str
    ethertype: str
    frame_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_l2_protocols(
    interface: str,
    *,
    listen_seconds: float = 1.5,
) -> list[L2ProtocolHit]:
    hits: dict[int, int] = {}
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
        sock.bind((interface, 0))
        sock.settimeout(0.25)
    except OSError as exc:
        logger.debug("L2 ethertype probe unavailable on %s: %s", interface, exc)
        return []

    deadline = datetime.now(timezone.utc).timestamp() + listen_seconds
    try:
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                frame = sock.recv(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(frame) < 14:
                continue
            ethertype = struct.unpack("!H", frame[12:14])[0]
            if ethertype in _ETHERTYPES:
                hits[ethertype] = hits.get(ethertype, 0) + 1
    finally:
        sock.close()

    return [
        L2ProtocolHit(
            protocol=_ETHERTYPES[ethertype],
            ethertype=f"0x{ethertype:04x}",
            frame_count=count,
        )
        for ethertype, count in sorted(hits.items())
    ]


def probe_l2_snapshot(interface: str) -> dict[str, Any]:
    hits = probe_l2_protocols(interface)
    return {
        "interface": interface,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "hits": [hit.to_dict() for hit in hits],
    }
