import threading
import time

from ndp.core.config import NdpConfig
from ndp.ui.discovery_session import DiscoveryUISession


def test_discovery_session_idle_lines() -> None:
    session = DiscoveryUISession(NdpConfig(interface="eth0"))
    lines = session.display_lines()
    assert "Up/Down" in lines[0]
    assert session.is_idle()


def test_discovery_idle_after_finished_thread() -> None:
    session = DiscoveryUISession(NdpConfig(interface="eth0"))
    session._running = False
    session._thread = threading.Thread(target=time.sleep, args=(0,))
    session._thread.start()
    session._thread.join()
    assert session.is_idle()


def test_discovery_on_select_starts_when_idle() -> None:
    session = DiscoveryUISession(NdpConfig(interface="eth0"))
    started = False

    def fake_start() -> None:
        nonlocal started
        started = True
        session._running = True

    session.start = fake_start  # type: ignore[method-assign]
    assert session.on_select() is True
    assert started
