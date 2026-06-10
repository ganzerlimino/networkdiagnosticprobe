import json
from pathlib import Path

from ndp.core.collectors.lldp import _parse_neighbor_payload


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_neighbor_payload_from_fixture() -> None:
    payload = json.loads((FIXTURES / "lldpctl_sample.json").read_text(encoding="utf-8"))
    neighbor = _parse_neighbor_payload(payload, "eth0")

    assert neighbor.available is True
    assert neighbor.protocol == "LLDP"
    assert neighbor.switch_name == "sw-core-01"
    assert neighbor.port_id == "1/1/24"
    assert neighbor.vlan_id == "120"
    assert neighbor.chassis_id == "00:11:22:33:44:55"
    assert neighbor.age_seconds == 12


def test_parse_neighbor_payload_missing_interface() -> None:
    neighbor = _parse_neighbor_payload({"lldp": {"interface": []}}, "eth0")
    assert neighbor.available is False
    assert neighbor.message == "no neighbor data"
