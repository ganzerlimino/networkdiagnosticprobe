"""SNMP probing (UDP 161) and trap port check (UDP 162)."""

from __future__ import annotations

import logging
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_COMMUNITIES = ("public", "private", "ro", "snmp")
_SYS_DESCR_OID = (1, 3, 6, 1, 2, 1, 1, 1, 0)
_TIMEOUT = 1.5


@dataclass
class SnmpProbeResult:
    host: str
    port: int
    reachable: bool
    community: str | None = None
    sys_descr: str | None = None
    error: str | None = None
    trap_port_open: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _encode_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(value)) + value


def _encode_oid(oid: tuple[int, ...]) -> bytes:
    if not oid:
        return b""
    first, second, *rest = oid
    body = bytes([40 * first + second])
    for part in rest:
        chunks: list[int] = []
        value = part
        chunks.append(value & 0x7F)
        value >>= 7
        while value:
            chunks.append(0x80 | (value & 0x7F))
            value >>= 7
        body += bytes(reversed(chunks))
    return body


def _build_snmp_get(community: str, oid: tuple[int, ...]) -> bytes:
    oid_bytes = _encode_oid(oid)
    var_bind = _encode_tlv(0x30, _encode_tlv(0x06, oid_bytes) + _encode_tlv(0x05, b""))
    var_bind_list = _encode_tlv(0x30, var_bind)
    get_pdu = (
        _encode_tlv(0x02, b"\x01")
        + _encode_tlv(0x02, b"\x00")
        + _encode_tlv(0x02, b"\x00")
        + _encode_tlv(0x02, b"\x00")
        + var_bind_list
    )
    pdu = _encode_tlv(0xA0, get_pdu)
    message = _encode_tlv(0x02, b"\x01") + _encode_tlv(0x04, community.encode("ascii")) + pdu
    return _encode_tlv(0x30, message)


def _decode_snmp_string(payload: bytes) -> str | None:
    for idx in range(len(payload) - 2):
        if payload[idx] != 0x04:
            continue
        value_len = payload[idx + 1]
        if value_len <= 0 or idx + 2 + value_len > len(payload):
            continue
        value = payload[idx + 2 : idx + 2 + value_len]
        if not value or value[0] < 0x20:
            continue
        try:
            text = value.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            continue
        if text:
            return text
    return None


def _udp_port_open(host: str, port: int, *, timeout: float = 0.5) -> bool:
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(b"\x00", (host, port))
        try:
            sock.recvfrom(512)
        except socket.timeout:
            pass
        return True
    except OSError:
        return False
    finally:
        if sock is not None:
            sock.close()


def probe_snmp(
    host: str,
    *,
    communities: tuple[str, ...] = _DEFAULT_COMMUNITIES,
    timeout_seconds: float = _TIMEOUT,
) -> SnmpProbeResult:
    result = SnmpProbeResult(host=host, port=161, reachable=False)
    result.trap_port_open = _udp_port_open(host, 162)

    for community in communities:
        request = _build_snmp_get(community, _SYS_DESCR_OID)
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout_seconds)
            sock.sendto(request, (host, 161))
            data, _addr = sock.recvfrom(4096)
            if not data:
                continue
            sys_descr = _decode_snmp_string(data)
            result.reachable = True
            result.community = community
            result.sys_descr = sys_descr
            if not sys_descr:
                result.error = "risposta SNMP senza sysDescr decodificabile"
            return result
        except socket.timeout:
            continue
        except OSError as exc:
            result.error = str(exc)
            continue
        finally:
            if sock is not None:
                sock.close()

    if not result.error:
        result.error = "nessuna risposta SNMP con community note"
    return result


def probe_snmp_snapshot(host: str | None, *, gateway: str | None = None) -> dict[str, Any]:
    target = host or gateway
    if not target:
        return {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "available": False,
            "message": "nessun host target (specificare host o gateway)",
            "result": None,
        }

    result = probe_snmp(target)
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "available": True,
        "message": "ok" if result.reachable else result.error or "no response",
        "result": result.to_dict(),
    }
