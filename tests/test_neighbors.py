from ndp.core.collectors.neighbors import _merge_neighbor_details
from ndp.core.state import NeighborState


def test_merge_neighbor_details_keeps_lldp_port_and_mndp_identity() -> None:
    lldp = NeighborState(
        protocol="LLDP",
        available=True,
        switch_name="sw01",
        port_id="br1/ether21",
        vlan_id="120",
        chassis_id="6c:3b:6b:aa:bb:cc",
    )
    mndp = NeighborState(
        protocol="MNDP",
        available=True,
        identity="sw01",
        board="CRS326-24G-2S+",
        chassis_id="6c:3b:6b:aa:bb:cc",
        port_id="bridge",
    )
    merged = _merge_neighbor_details(lldp, mndp)
    assert merged.port_id == "br1/ether21"
    assert merged.vlan_id == "120"
    assert merged.identity == "sw01"
    assert merged.board == "CRS326-24G-2S+"


def test_merge_neighbor_details_ignores_unavailable_secondary() -> None:
    lldp = NeighborState(protocol="LLDP", available=True, switch_name="sw1", port_id="Gi0/1")
    mndp = NeighborState(protocol="MNDP", available=False, message="no mndp neighbor")
    merged = _merge_neighbor_details(lldp, mndp)
    assert merged.switch_name == "sw1"
    assert merged.port_id == "Gi0/1"
