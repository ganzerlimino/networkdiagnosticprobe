from ndp.ui.buttons import ButtonAction, PhysicalButtons


def test_level_trigger_fires_once_until_release() -> None:
    buttons = PhysicalButtons(debounce_seconds=0.0, press_confirm_ms=0, trigger_mode="level")
    pin = buttons.mapping.previous
    fired: list[ButtonAction] = []

    buttons._poll_level(pin, ButtonAction.PREVIOUS, 0, 1.0, 0.0, fired.append)
    buttons._poll_level(pin, ButtonAction.PREVIOUS, 0, 1.01, 0.0, fired.append)
    assert fired == [ButtonAction.PREVIOUS]

    buttons._poll_level(pin, ButtonAction.PREVIOUS, 1, 1.1, 0.0, fired.append)
    buttons._poll_level(pin, ButtonAction.PREVIOUS, 0, 1.2, 0.0, fired.append)
    assert fired == [ButtonAction.PREVIOUS, ButtonAction.PREVIOUS]


def test_press_confirm_ms_delays_trigger() -> None:
    buttons = PhysicalButtons(debounce_seconds=0.0, press_confirm_ms=50, trigger_mode="level")
    pin = buttons.mapping.select
    fired: list[ButtonAction] = []

    buttons._poll_level(pin, ButtonAction.SELECT, 0, 1.0, 0.05, fired.append)
    assert fired == []

    buttons._poll_level(pin, ButtonAction.SELECT, 0, 1.06, 0.05, fired.append)
    assert fired == [ButtonAction.SELECT]
