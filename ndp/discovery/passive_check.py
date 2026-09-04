"""Passive L2 broadcast/multicast frame detection (STP, LACP, VLAN, IGMP, …)."""

from __future__ import annotations

import logging
import socket
import struct
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_STP_MAC = bytes.fromhex("0180c2000000")
_LACP_MAC = bytes.fromhex("0180c2000002")
_VTP_MAC = bytes.fromhex("01000ccccccc")
_ISL_MAC = bytes.fromhex("01000c000000")
_IGMP_MAC_PREFIX = bytes.fromhex("01005e")

_ETHERTYPE_VLAN = 0x8100
_ETHERTYPE_QINQ = 0x88A8
_ETHERTYPE_IPV4 = 0x0800
_ETHERTYPE_ISL = 0x0000


@dataclass
class PassiveProtocolHit:
    protocol: str
    variant: str | None = None
    frame_count: int = 0
    samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PassiveCheckSnapshot:
    interface: str
    listen_seconds: float
    scanned_at: datetime
    available: bool
    message: str
    hits: list[PassiveProtocolHit] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interface": self.interface,
            "listen_seconds": self.listen_seconds,
            "scanned_at": self.scanned_at.isoformat(),
            "available": self.available,
            "message": self.message,
            "hits": [hit.to_dict() for hit in self.hits],
        }


def _mac_match(dest: bytes, expected: bytes) -> bool:
    return len(dest) >= len(expected) and dest[: len(expected)] == expected


def _bridge_group_mac(dest: bytes) -> bool:
    return len(dest) == 6 and dest[:5] == _STP_MAC[:5] and (dest[5] & 0xF0) == 0x00


def _parse_vlan_stack(frame: bytes, offset: int) -> tuple[list[int], int, int | None]:
    """Return VLAN IDs, next offset, and inner ethertype if present."""
    vlans: list[int] = []
    inner_ethertype: int | None = None

    while offset + 4 <= len(frame):
        field_type = struct.unpack("!H", frame[offset : offset + 2])[0]
        if field_type not in (_ETHERTYPE_VLAN, _ETHERTYPE_QINQ, 0x9100):
            inner_ethertype = field_type
            break
        tci = struct.unpack("!H", frame[offset + 2 : offset + 4])[0]
        vlans.append(tci & 0x0FFF)
        offset += 4

    return vlans, offset, inner_ethertype


def _parse_stp_variant(payload: bytes) -> str:
    if len(payload) < 6:
        return "STP"
    if payload[0:2] != b"\x00\x00":
        return "STP"
    version = payload[2]
    if version == 0:
        return "STP"
    if version == 2:
        return "RSTP"
    if version >= 3:
        return "MSTP"
    return "STP"


def _classify_8023_payload(frame: bytes, offset: int) -> list[tuple[str, str | None, str]]:
    results: list[tuple[str, str | None, str]] = []
    if offset + 5 > len(frame):
        return results

    dsap, ssap, control = frame[offset], frame[offset + 1], frame[offset + 2]
    if dsap == 0x42 and ssap == 0x42 and control == 0x03:
        if offset + 4 <= len(frame):
            subtype = frame[offset + 3]
            if subtype == 0x01:
                results.append(("LACP", "802.3ad", "slow-protocol subtype 0x01"))
            elif subtype in {0x02, 0x03}:
                results.append(("LACP", "slow-protocol", f"subtype 0x{subtype:02x}"))
        bpdu = frame[offset + 3 :]
        if len(bpdu) >= 3 and bpdu[0:2] == b"\x00\x00":
            variant = _parse_stp_variant(bpdu)
            results.append(("Spanning Tree", variant, f"BPDU v{bpdu[2]}"))
    return results


def _classify_frame(frame: bytes) -> list[tuple[str, str | None, str]]:
    if len(frame) < 14:
        return []

    dest = frame[0:6]
    results: list[tuple[str, str | None, str]] = []

    if _mac_match(dest, _IGMP_MAC_PREFIX):
        results.append(("IGMP", "multicast-mac", dest.hex(":")))

    if _mac_match(dest, _VTP_MAC):
        results.append(("VTP", "Cisco", "dst 01:00:0c:cc:cc:cc"))

    if _mac_match(dest, _ISL_MAC):
        results.append(("ISL", "Cisco", "dst 01:00:0c:00:00:00"))

    if len(frame) >= 16 and frame[12:16] == b"\xaa\xaa\x03\x00":
        results.append(("ISL", "encap", "AA AA 03 00 header"))

    length_or_type = struct.unpack("!H", frame[12:14])[0]

    if length_or_type <= 1500:
        results.extend(_classify_8023_payload(frame, 14))
        if _bridge_group_mac(dest) or _mac_match(dest, _STP_MAC):
            if not any(item[0] == "Spanning Tree" for item in results):
                results.append(("Spanning Tree", "unknown", "bridge-group MAC"))
        if _mac_match(dest, _LACP_MAC) and not any(item[0] == "LACP" for item in results):
            results.append(("LACP", "802.3ad", "slow-protocols multicast"))
        return results

    vlans, next_offset, inner_ethertype = _parse_vlan_stack(frame, 12)
    if vlans:
        tag_type = "802.1Q"
        if length_or_type == _ETHERTYPE_QINQ:
            tag_type = "Q-in-Q"
        results.append(("VLAN", tag_type, f"tags={','.join(str(v) for v in vlans)}"))

    ethertype = inner_ethertype if inner_ethertype is not None else length_or_type
    if ethertype == _ETHERTYPE_IPV4 and next_offset + 20 <= len(frame):
        ip_start = next_offset
        version_ihl = frame[ip_start]
        ihl = (version_ihl & 0x0F) * 4
        if ip_start + ihl + 1 <= len(frame):
            protocol = frame[ip_start + 9]
            if protocol == 2:  # IGMP
                igmp_offset = ip_start + ihl
                if igmp_offset < len(frame):
                    igmp_type = frame[igmp_offset]
                    igmp_name = {
                        0x11: "Membership Query v2",
                        0x12: "v1 Report",
                        0x16: "v2 Report",
                        0x17: "Leave",
                        0x22: "v3 Report",
                        0x82: "Membership Query v3",
                    }.get(igmp_type, f"type 0x{igmp_type:02x}")
                    results.append(("IGMP", igmp_name, "IPv4 proto 2"))

    if _mac_match(dest, _LACP_MAC):
        if not any(item[0] == "LACP" for item in results):
            results.append(("LACP", "802.3ad", "dst 01:80:c2:00:00:02"))
    if _bridge_group_mac(dest) or _mac_match(dest, _STP_MAC):
        if not any(item[0] == "Spanning Tree" for item in results):
            results.append(("Spanning Tree", "unknown", "bridge-group MAC"))

    return results


def sniff_passive_protocols(
    interface: str,
    *,
    listen_seconds: float = 3.0,
) -> PassiveCheckSnapshot:
    scanned_at = datetime.now(timezone.utc)
    aggregated: dict[tuple[str, str | None], PassiveProtocolHit] = {}

    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
        sock.bind((interface, 0))
        sock.settimeout(0.25)
    except OSError as exc:
        logger.warning("Passive check unavailable on %s: %s", interface, exc)
        return PassiveCheckSnapshot(
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

            for protocol, variant, sample in _classify_frame(frame):
                key = (protocol, variant)
                hit = aggregated.get(key)
                if hit is None:
                    hit = PassiveProtocolHit(protocol=protocol, variant=variant, frame_count=0)
                    aggregated[key] = hit
                hit.frame_count += 1
                if sample not in hit.samples and len(hit.samples) < 5:
                    hit.samples.append(sample)
    finally:
        sock.close()

    hits = sorted(aggregated.values(), key=lambda item: (-item.frame_count, item.protocol))
    if hits:
        message = f"{sum(hit.frame_count for hit in hits)} frame rilevati"
        available = True
    else:
        message = "nessun frame broadcast/multicast rilevato nel periodo di ascolto"
        available = True

    return PassiveCheckSnapshot(
        interface=interface,
        listen_seconds=listen_seconds,
        scanned_at=scanned_at,
        available=available,
        message=message,
        hits=hits,
    )
