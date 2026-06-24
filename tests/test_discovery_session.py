from ndp.core.config import NdpConfig
from ndp.ui.discovery_session import DiscoveryUISession


def test_discovery_session_idle_lines() -> None:
    session = DiscoveryUISession(NdpConfig(interface="eth0"))
    lines = session.display_lines()
    assert "Up/Down" in lines[0]
    assert session.is_idle()
