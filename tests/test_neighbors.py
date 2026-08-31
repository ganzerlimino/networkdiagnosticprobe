from ndp.core.collectors.lldp import _consolidate_lldp_candidates
from ndp.core.collectors.neighbors import _merge_neighbor_details
from ndp.core.state import NeighborState


def test_consolidate_lldp_merges_port_vlan_across_neighbors() -> None:
    candidates = [
        NeighborState(
            available=True,
            protocol="LLDP",
            switch_name="sw01",
            chassis_id="6c:3b:6b:aa:bb:cc",
            age_seconds=12,
        ),
        NeighborState(
            available=True,
            protocol="LLDP",
            port_id="br1/ether21",
            vlan_id="120",
            age_seconds=40,
        ),
    ]
    merged = _consolidate_lldp_candidates(candidates)
    assert merged.available is True
    assert merged.switch_name == "sw01"
    assert merged.port_id == "br1/ether21"
    assert merged.vlan_id == "120"


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


def test_merge_neighbor_details_uses_mndp_port_when_lldp_port_weak() -> None:
    lldp = NeighborState(
        protocol="LLDP",
        available=True,
        switch_name="sw01",
        port_id="bridge",
        chassis_id="6c:3b:6b:aa:bb:cc",
    )
    mndp = NeighborState(
        protocol="MNDP",
        available=True,
        identity="sw01",
        port_id="br1/ether21",
        chassis_id="6c:3b:6b:aa:bb:cc",
    )
    merged = _merge_neighbor_details(lldp, mndp)
    assert merged.port_id == "br1/ether21"


def test_combine_neighbors_merges_mndp_identity_with_lldp_topology() -> None:
    from ndp.core.collectors.neighbors import _combine_neighbors

    lldp = NeighborState(protocol="LLDP", available=False, message="no neighbor data")
    mndp = NeighborState(
        protocol="MNDP",
        available=True,
        identity="sw01",
        port_id="ether21",
        board="CRS326-24G-2S+",
    )
    merged = _combine_neighbors(lldp, mndp)
    assert merged.available is True
    assert merged.identity == "sw01"
    assert merged.port_id == "ether21"


def test_combine_neighbors_reports_both_protocol_failures() -> None:
    from ndp.core.collectors.neighbors import _combine_neighbors

    lldp = NeighborState(protocol="LLDP", available=False, message="no neighbor data")
    mndp = NeighborState(protocol="MNDP", available=False, message="no mndp neighbor")
    merged = _combine_neighbors(lldp, mndp)
    assert merged.available is False
    assert "LLDP: no neighbor data" in merged.message
    assert "MNDP: no mndp neighbor" in merged.message


def test_neighbor_from_mndp_device_maps_interface_to_port() -> None:
    from ndp.core.collectors.neighbors import neighbor_from_mndp_device

    neighbor = neighbor_from_mndp_device(
        {
            "identity": "sw01",
            "mac": "6c:3b:6b:aa:bb:cc",
            "interface": "br1/ether21",
            "board": "CRS326-24G-2S+",
        }
    )
    assert neighbor.port_id == "br1/ether21"
    assert neighbor.switch_name == "sw01"


def test_merge_neighbor_details_ignores_unavailable_secondary() -> None:
    lldp = NeighborState(protocol="LLDP", available=True, switch_name="sw1", port_id="Gi0/1")
    mndp = NeighborState(protocol="MNDP", available=False, message="no mndp neighbor")
    merged = _merge_neighbor_details(lldp, mndp)
    assert merged.switch_name == "sw1"
    assert merged.port_id == "Gi0/1"
