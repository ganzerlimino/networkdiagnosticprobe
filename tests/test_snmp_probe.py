from ndp.discovery.snmp_probe import _build_snmp_get, _decode_snmp_string


def test_build_snmp_get_packet() -> None:
    packet = _build_snmp_get("public", (1, 3, 6, 1, 2, 1, 1, 1, 0))
    assert packet.startswith(b"\x30")
    assert b"public" in packet


def test_decode_snmp_string_from_octet_string() -> None:
    payload = b"\x30\x20\xa2\x18\x04\x09Cisco IOS"
    assert _decode_snmp_string(payload) == "Cisco IOS"
