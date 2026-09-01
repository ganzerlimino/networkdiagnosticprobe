from ndp.core.config import NdpConfig
from ndp.ui.screens import lines_for_screen, screen_title, shutdown_lines, tft_text
from ndp.ui.screens import ScreenId
from ndp.core.state import ProbeState


def test_screen_title_uses_locale() -> None:
    config = NdpConfig(ui_locale="de")
    assert screen_title(ScreenId.HOME, config) == "Home"
    assert tft_text(config, "tft.shutdown_title") == "HERUNTERFAHREN"


def test_shutdown_lines_german() -> None:
    config = NdpConfig(ui_locale="de")
    lines = shutdown_lines(config=config)
    assert lines[0] == "HERUNTERFAHREN"
    assert "trennen" in lines[-1]


def test_lines_for_screen_german_switch_down() -> None:
    config = NdpConfig(ui_locale="de")
    state = ProbeState(interface="eth0")
    state.link.carrier = False
    lines = lines_for_screen(ScreenId.SWITCH, state, config=config)
    assert lines[0] == "Link down"
    assert "Kabel" in lines[1]
