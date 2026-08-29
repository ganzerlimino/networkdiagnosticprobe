from ndp.core.collectors.neighbors import NeighborCollection
from ndp.core.config import NdpConfig
from ndp.core.engine import ProbeEngine
from ndp.core.state import LinkState, NeighborState


def test_neighbor_cache_keeps_last_good_value(monkeypatch) -> None:
    config = NdpConfig(interface="eth0", lldp_cache_ttl_seconds=30)
    engine = ProbeEngine(config)
    engine.state.link = LinkState(operstate="up", carrier=True)

    good = NeighborState(
        available=True,
        switch_name="sw-a",
        port_id="Gi0/1",
        message="ok",
    )
    empty = NeighborState(available=False, message="waiting")

    calls = {"count": 0}

    def fake_collect(_interface: str, **kwargs: object) -> NeighborCollection:
        calls["count"] += 1
        neighbor = good if calls["count"] == 1 else empty
        return NeighborCollection(primary=neighbor, entries=[neighbor])

    monkeypatch.setattr("ndp.core.engine.collect_neighbors", fake_collect)
    monkeypatch.setattr(
        "ndp.core.engine.collect_link_state",
        lambda _interface: LinkState(operstate="up", carrier=True),
    )
    monkeypatch.setattr("ndp.core.engine.collect_ip_state", lambda _interface: engine.state.ip)
    monkeypatch.setattr(
        "ndp.core.engine.collect_system_state",
        lambda: engine.state.system,
    )

    first = engine.refresh()
    second = engine.refresh()

    assert first.neighbor.switch_name == "sw-a"
    assert second.neighbor.switch_name == "sw-a"
    assert "cached" in second.neighbor.message
