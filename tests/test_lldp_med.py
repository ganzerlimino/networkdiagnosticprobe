import json
from pathlib import Path

from ndp.core.collectors.lldp import _parse_neighbor_payload


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_neighbor_payload_med_and_poe() -> None:
    payload = json.loads((FIXTURES / "lldpctl_med_poe.json").read_text(encoding="utf-8"))
    neighbor = _parse_neighbor_payload(payload, "eth0")

    assert neighbor.available is True
    assert neighbor.med_device_type == "Endpoint Class I"
    assert neighbor.med_capabilities == "Capabilities"
    assert neighbor.poe_status == "delivering"
    assert neighbor.poe_allocated_w == 15.4
    assert neighbor.poe_requested_w == 13.0
