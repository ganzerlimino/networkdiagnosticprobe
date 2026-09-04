from ndp.discovery.epson_enpc import parse_enpc_response
from ndp.discovery.printers import discover_printers_snapshot
from ndp.discovery.zebra_discovery import parse_zebra_discovery_response


def test_parse_enpc_response_extracts_model_and_mac() -> None:
    payload = bytearray(48)
    payload[0:5] = b"EPSON"
    payload[5:13] = bytes([0x51, 0x03, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00])
    payload[16:22] = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
    payload[24:28] = bytes([192, 168, 1, 45])
    payload[32:40] = b"TM-T88VI\x00"
    device = parse_enpc_response(bytes(payload), "192.168.1.99")
    assert device is not None
    assert device.host == "192.168.1.45"
    assert device.mac == "aa:bb:cc:dd:ee:ff"
    assert device.model == "TM-T88VI"


def test_parse_enpc_response_rejects_invalid_payload() -> None:
    assert parse_enpc_response(b"NOPE", "192.168.1.10") is None


def test_parse_zebra_discovery_response_extracts_product_and_hostname() -> None:
    payload = (
        b":,.\x03"
        + b"ZD420"
        + b"\x00"
        + b"\x00" * 8
        + bytes([10, 1, 0, 120])
        + bytes([255, 255, 255, 0])
        + bytes([10, 1, 0, 1])
        + b"ZBR4262077\x00"
    )
    device = parse_zebra_discovery_response(payload, "192.168.1.60")
    assert device is not None
    assert device.product == "ZD420"
    assert device.hostname == "ZBR4262077"
    assert device.host == "192.168.1.60"


def test_parse_zebra_discovery_response_rejects_invalid_payload() -> None:
    assert parse_zebra_discovery_response(b"invalid", "192.168.1.10") is None


def test_discover_printers_snapshot_shape(monkeypatch) -> None:
    from ndp.discovery.epson_enpc import EnpcDevice
    from ndp.discovery.zebra_discovery import ZebraDevice

    monkeypatch.setattr(
        "ndp.discovery.printers.discover_epson_enpc",
        lambda _interface, timeout_seconds=3.0: [
            EnpcDevice(host="192.168.1.45", mac="aa:bb:cc:dd:ee:ff", model="TM-T88VI"),
        ],
    )
    monkeypatch.setattr(
        "ndp.discovery.printers.discover_zebra_printers",
        lambda _interface, timeout_seconds=3.0: [
            ZebraDevice(host="192.168.1.60", product="ZD420", hostname="ZBR4262077"),
        ],
    )

    snapshot = discover_printers_snapshot("eth0", timeout_seconds=2.0)
    assert snapshot["device_count"] == 2
    assert snapshot["epson_count"] == 1
    assert snapshot["zebra_count"] == 1
    vendors = {device["vendor"] for device in snapshot["devices"]}
    assert vendors == {"Epson", "Zebra"}
