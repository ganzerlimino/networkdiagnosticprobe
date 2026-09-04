from unittest.mock import patch

from ndp.scan.ports import parse_custom_ports, scan_ports
from ndp.scan.profiles import profiles_catalog, profile_ports


def test_parse_custom_ports_csv() -> None:
    assert parse_custom_ports("80, 443, 502") == [80, 443, 502]


def test_parse_custom_ports_rejects_invalid() -> None:
    try:
        parse_custom_ports("80,abc")
        assert False
    except ValueError:
        pass


def test_industrial_profile_contains_modbus_opc_mqtt() -> None:
    ports = {item.port for item in profile_ports("industrial")}
    assert 502 in ports
    assert 4840 in ports
    assert 1883 in ports
    assert 44818 in ports


def test_standard_profile_contains_common_it_ports() -> None:
    ports = {item.port for item in profile_ports("standard")}
    assert {22, 80, 443, 445, 3389}.issubset(ports)


def test_profiles_catalog() -> None:
    catalog = profiles_catalog()
    assert "standard" in catalog["profiles"]
    assert "industrial" in catalog["profiles"]


def test_scan_ports_marks_open() -> None:
    def fake_probe(host: str, port: int, timeout_seconds: float):
        return port == 80, 3.5 if port == 80 else None

    with patch("ndp.scan.ports.probe_tcp_port", side_effect=fake_probe):
        result = scan_ports("10.0.0.1", "custom", custom_ports=[80, 443])

    assert result.host == "10.0.0.1"
    open_ports = {entry.port for entry in result.open_ports}
    assert open_ports == {80}
