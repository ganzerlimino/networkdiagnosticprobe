from ndp.core.collectors.neighbors import neighbor_from_mndp_device
from ndp.core.config import NdpConfig
from ndp.core.engine import ProbeEngine
from ndp.core.state import LinkState, NeighborState


def test_apply_mndp_device_merges_port_into_neighbor() -> None:
    engine = ProbeEngine(NdpConfig(interface="eth0"))
    engine.state.link = LinkState(operstate="up", carrier=True)
    engine.state.neighbor = NeighborState(
        available=True,
        protocol="MNDP",
        switch_name="sw01",
        identity="sw01",
        message="ok",
    )

    merged = engine.apply_mndp_device(
        {
            "identity": "sw01",
            "mac": "6c:3b:6b:aa:bb:cc",
            "interface": "br1/ether21",
            "board": "CRS326-24G-2S+",
        }
    )

    assert merged.port_id == "br1/ether21"
    assert merged.switch_name == "sw01"


def test_neighbor_from_mndp_device_maps_interface_to_port() -> None:
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
