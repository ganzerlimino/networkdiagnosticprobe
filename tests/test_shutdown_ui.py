from ndp.ui.screens import shutdown_lines, shutdown_palette, shutdown_phase_message
from ndp.core.config import NdpConfig


def test_shutdown_lines() -> None:
    lines = shutdown_lines("Arresto in corso")
    assert lines[0] == "SPEGNIMENTO"
    assert "Arresto in corso" in lines


def test_shutdown_palette_is_high_visibility_red() -> None:
    palette = shutdown_palette()
    assert palette["bg"][0] > palette["bg"][1]
    assert palette["text"] == (255, 255, 255)


def test_shutdown_phase_message_uses_locale() -> None:
    config = NdpConfig(ui_locale="en")
    assert shutdown_phase_message("powering_off", config) == "Powering off..."
