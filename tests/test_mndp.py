import struct

from ndp.core.collectors.mndp import (
    MNDP_PORT,
    _MNDP_REFRESH,
    _MNDP_REFRESH_TLV,
    parse_mndp_payload,
)


def _tlv(tlv_type: int, value: bytes) -> bytes:
    return struct.pack("!HH", tlv_type, len(value)) + value


def test_mndp_refresh_probes() -> None:
    assert _MNDP_REFRESH == b"\x00\x00\x00\x00"
    assert _MNDP_REFRESH_TLV == bytes.fromhex("000000000006000000")
    assert MNDP_PORT == 5678


def test_parse_mndp_payload_tlv_fields() -> None:
    payload = b"\x00\x01\x00\x02"  # header + sequence
    payload += _tlv(5, b"MikroTik-Core")
    payload += _tlv(12, b"RB4011")
    payload += _tlv(16, b"ether1")
    payload += _tlv(17, bytes([192, 168, 1, 1]))
    payload += _tlv(7, b"7.15.2")

    fields = parse_mndp_payload(payload)
    assert fields["identity"] == "MikroTik-Core"
    assert fields["board"] == "RB4011"
    assert fields["interface"] == "ether1"
    assert fields["ipv4"] == "192.168.1.1"
    assert fields["version"] == "7.15.2"
