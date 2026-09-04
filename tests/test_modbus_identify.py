from ndp.discovery.modbus_identify import parse_modbus_device_id_response


def _build_device_id_response(objects: list[tuple[int, str]]) -> bytes:
    body = bytearray([0x01, 0x2B, 0x0E, 0x01, 0x01, 0x00, 0x00, len(objects)])
    for object_id, value in objects:
        encoded = value.encode("ascii")
        body.extend([object_id, len(encoded)])
        body.extend(encoded)
    header = bytes([0x00, 0x01, 0x00, 0x00]) + len(body).to_bytes(2, "big")
    return header + bytes(body)


def test_parse_modbus_device_id_response_extracts_objects() -> None:
    payload = _build_device_id_response([
        (0x00, "ACME PLC"),
        (0x04, "Drive X"),
    ])
    parsed = parse_modbus_device_id_response(payload)
    assert parsed["conformity_level"] == 1
    assert parsed["objects"]["vendor_name"] == "ACME PLC"
    assert parsed["objects"]["product_name"] == "Drive X"
