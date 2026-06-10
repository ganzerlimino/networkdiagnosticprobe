from ndp.console import render_status
from ndp.core.state import IpAddress, IpState, LinkState, NeighborState, ProbeState, SystemState


def test_render_status_contains_key_sections() -> None:
    state = ProbeState(
        interface="eth0",
        link=LinkState(operstate="up", carrier=True, mac_address="aa:bb:cc:dd:ee:ff"),
        ip=IpState(
            addresses=[IpAddress(family="inet", address="10.0.0.50", prefixlen=24)],
            gateway="10.0.0.1",
            dns_servers=["10.0.0.1"],
        ),
        neighbor=NeighborState(
            available=True,
            protocol="LLDP",
            switch_name="sw-core",
            port_id="1/1/1",
            vlan_id="10",
            message="ok",
        ),
        system=SystemState(hostname="ndp", uptime_seconds=120.5, cpu_temperature_c=48.2),
    )

    output = render_status(state)

    assert "Network Diagnostic Probe" in output
    assert "sw-core" in output
    assert "10.0.0.50/24" in output
    assert "ndp" in output
