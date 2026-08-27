from ndp.core.state import IpAddress, IpState, LinkState, NeighborState, ProbeState, SystemState
from ndp.ui.screens import ScreenId, lines_for_screen, next_screen, screen_ids_for_mode


def test_next_screen_cycles() -> None:
    assert next_screen(ScreenId.HOME) == ScreenId.SWITCH
    assert next_screen(ScreenId.NETWORK) == ScreenId.PING
    assert next_screen(ScreenId.PING) == ScreenId.SYSTEM
    assert next_screen(ScreenId.DISCOVER) == ScreenId.HOME
    assert next_screen(ScreenId.HOME, -1) == ScreenId.DISCOVER


def test_display_mode_excludes_discover() -> None:
    screens = screen_ids_for_mode(interactive=False)
    assert ScreenId.DISCOVER not in screens
    assert next_screen(ScreenId.SYSTEM, 1, screens=screens) == ScreenId.HOME


def test_ping_screen_read_only_hint() -> None:
    state = ProbeState(interface="eth0")
    lines = lines_for_screen(ScreenId.PING, state, interactive=False, web_port=8080)
    assert any(":8080" in line for line in lines)
    assert not any("○" in line for line in lines)


def test_home_screen_lines() -> None:
    state = ProbeState(
        interface="eth0",
        link=LinkState(carrier=True, mac_address="aa:bb:cc:dd:ee:ff"),
        ip=IpState(addresses=[IpAddress(family="inet", address="10.0.0.5", prefixlen=24)]),
        system=SystemState(hostname="ndp"),
    )
    lines = lines_for_screen(ScreenId.HOME, state)
    assert any("10.0.0.5/24" in line for line in lines)
    assert any("ndp" in line for line in lines)


def test_switch_screen_waiting_message() -> None:
    state = ProbeState(
        interface="eth0",
        link=LinkState(carrier=True),
        neighbor=NeighborState(available=False, message="waiting"),
    )
    lines = lines_for_screen(ScreenId.SWITCH, state)
    assert "waiting" in lines[1]
