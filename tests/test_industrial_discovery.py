from ndp.discovery.ewon import (
    parse_ipconf_device_info,
    parse_ipconf_firmware_info,
    parse_ipconf_response,
)
from ndp.discovery.oui import lookup_vendor, oui_table, reload_oui_database
from ndp.discovery.weintek_hmi import parse_weintek_response


def test_parse_weintek_plaintext_response() -> None:
    payload = (
        "cMT-SVR-100\n"
        "192.168.10.50\n"
        "255.255.255.0\n"
        "00:90:E8:12:34:56\n"
        "V6.08.02.500\n"
    ).encode("utf-8")
    device = parse_weintek_response(payload, "192.168.10.1", port=60000)
    assert device is not None
    assert device.name == "cMT-SVR-100"
    assert device.host == "192.168.10.50"
    assert device.subnet_mask == "255.255.255.0"
    assert device.mac == "00:90:E8:12:34:56"
    assert device.firmware == "V6.08.02.500"
    assert device.discovery_port == 60000


def test_parse_weintek_mt8071_model() -> None:
    payload = b"MT8071iE 192.168.1.20 255.255.255.0 00-90-E8-00-11-22 firmware: 20231011"
    device = parse_weintek_response(payload, "192.168.1.1")
    assert device is not None
    assert device.name == "MT8071iE"
    assert device.host == "192.168.1.20"
    assert device.mac == "00:90:E8:00:11:22"


def test_parse_ipconf_device_info() -> None:
    data = bytearray(38)
    data[0:4] = b"IPCO"
    data[15] = 2
    data[16] = 131
    data[20:24] = bytes([50, 0, 168, 192])  # 192.168.0.50 reversed
    data[24:28] = bytes([0, 255, 255, 255])
    data[32:38] = bytes([0x00, 0x05, 0xF5, 0x12, 0x34, 0x56])
    device = parse_ipconf_device_info(bytes(data))
    assert device is not None
    assert device.host == "192.168.0.50"
    assert device.netmask == "255.255.255.0"
    assert device.mac == "00:05:F5:12:34:56"
    assert device.model == "Cosy 131"


def test_parse_ipconf_firmware_response() -> None:
    data = bytearray(32)
    data[15] = 5
    data[20:27] = b"14.6s0\x00"
    assert parse_ipconf_firmware_info(bytes(data)) == "14.6s0"
    parsed = parse_ipconf_response(bytes(data))
    assert parsed is not None
    assert parsed.firmware == "14.6s0"


def test_bundled_oui_lookup_weintek_and_ewon() -> None:
    reload_oui_database()
    assert lookup_vendor("00:90:E8:11:22:33") == "Weintek Laboratory Inc."
    assert lookup_vendor("00:05:F5:AA:BB:CC") == "HMS Industrial Networks / eWON SA"


def test_oui_table_contains_bundled_entries() -> None:
    reload_oui_database()
    rows = oui_table(search="weintek", limit=20)
    assert any("Weintek" in row["vendor"] for row in rows)
