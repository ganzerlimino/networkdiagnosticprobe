from ndp.core.config import NdpConfig
from ndp.ui.discovery_session import DiscoveryUISession


def test_discovery_to_api_dict_idle() -> None:
    session = DiscoveryUISession(NdpConfig(interface="eth0"))
    payload = session.to_api_dict()
    assert payload["idle"] is True
    assert payload["phase"] == "idle"
    assert "prompt" in payload
