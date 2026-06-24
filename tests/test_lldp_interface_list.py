from ndp.core.collectors.lldp import _parse_neighbor_payload


def test_parse_neighbor_payload_skips_string_interface_entries() -> None:
    payload = {
        "lldp": {
            "interface": [
                "eth0",
                {
                    "name": "eth0",
                    "via": "LLDP",
                    "chassis": [{"name": {"value": "sw-a"}}],
                    "port": [{"id": {"value": "Gi0/1"}}],
                },
            ]
        }
    }
    neighbor = _parse_neighbor_payload(payload, "eth0")
    assert neighbor.available is True
    assert neighbor.switch_name == "sw-a"
