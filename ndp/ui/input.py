"""Factory for TFT UI input devices (buttons or rotary encoder)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ndp.core.config import NdpConfig
from ndp.ui.buttons import ButtonAction, ButtonMapping, PhysicalButtons
from ndp.ui.encoder import EncoderMapping, RotaryEncoder


class UIInputDevice(Protocol):
    def open(self) -> None: ...

    def close(self) -> None: ...

    def poll(self, handler: Callable[[ButtonAction], None]) -> None: ...

    def __enter__(self) -> UIInputDevice: ...

    def __exit__(self, *args: object) -> None: ...


def create_ui_input(config: NdpConfig) -> UIInputDevice:
    if config.ui_input == "encoder":
        return RotaryEncoder(
            EncoderMapping(
                clk=config.ui_encoder_clk,
                dt=config.ui_encoder_dt,
                sw=config.ui_encoder_sw,
            ),
            steps_per_detent=config.ui_encoder_steps_per_detent,
            sw_debounce_seconds=config.ui_encoder_sw_debounce_seconds,
        )

    return PhysicalButtons(
        ButtonMapping(
            previous=config.ui_button_previous,
            select=config.ui_button_select,
            next=config.ui_button_next,
        ),
        debounce_seconds=config.ui_button_debounce_seconds,
        trigger_mode=config.ui_button_trigger_mode,
        press_confirm_ms=config.ui_button_press_confirm_ms,
    )
