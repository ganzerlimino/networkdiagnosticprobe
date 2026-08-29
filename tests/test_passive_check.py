import struct

from ndp.discovery.dhcp_option82 import _parse_dhcp_packet, _parse_option82
from ndp.discovery.passive_check import _classify_frame


def _stp_frame(version: int) -> bytes:
    dest = bytes.fromhex("0180c2000000")
    src = bytes.fromhex("aabbccddeeff")
    llc = bytes([0x42, 0x42, 0x03])
    bpdu = b"\x00\x00" + bytes([version]) + b"\x00" * 20
    payload = llc + bpdu
    return dest + src + struct.pack("!H", len(payload)) + payload


def test_classify_rstp_frame() -> None:
    hits = _classify_frame(_stp_frame(2))
    protocols = {protocol for protocol, _variant, _sample in hits}
    assert "Spanning Tree" in protocols
    assert any(variant == "RSTP" for protocol, variant, _sample in hits if protocol == "Spanning Tree")


def test_classify_lacp_frame() -> None:
    dest = bytes.fromhex("0180c2000002")
    src = bytes.fromhex("aabbccddeeff")
    payload = bytes([0x42, 0x42, 0x03, 0x01, 0x01, 0x00])
    frame = dest + src + struct.pack("!H", len(payload)) + payload
    hits = _classify_frame(frame)
    assert any(protocol == "LACP" for protocol, _variant, _sample in hits)


def test_classify_vlan_tagged_frame() -> None:
    dest = bytes.fromhex("ffffffffffff")
    src = bytes.fromhex("aabbccddeeff")
    frame = dest + src + struct.pack("!HHH", 0x8100, 120, 0x0800)
    hits = _classify_frame(frame)
    assert any(protocol == "VLAN" for protocol, _variant, _sample in hits)


def test_parse_option82_suboptions() -> None:
    raw = b"\x01\x05vlan1\x02\x07switch1"
    circuit, remote = _parse_option82(raw)
    assert circuit == "vlan1"
    assert remote == "switch1"


def test_parse_dhcp_packet_with_option82() -> None:
    packet = bytearray(300)
    packet[0] = 1
    packet[28:34] = bytes.fromhex("aabbccddeeff")
    offset = 236
    packet[offset : offset + 4] = b"\x63\x82\x53\x63"
    offset += 4
    packet[offset : offset + 3] = bytes([53, 1, 1])
    offset += 3
    option82 = b"\x01\x04eth1"
    packet[offset : offset + 2] = bytes([82, len(option82)])
    offset += 2
    packet[offset : offset + len(option82)] = option82
    offset += len(option82)
    packet[offset] = 255

    sample = _parse_dhcp_packet(bytes(packet), "192.168.1.10")
    assert sample is not None
    assert sample.message_type == "DISCOVER"
    assert sample.circuit_id == "eth1"
