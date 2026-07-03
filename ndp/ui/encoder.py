"""KY-040 rotary encoder input (CLK/DT quadrature + SW click)."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass

from ndp.ui.buttons import ButtonAction

logger = logging.getLogger(__name__)

try:
    import lgpio
except ImportError:  # pragma: no cover - optional on dev machines
    lgpio = None  # type: ignore[assignment]

# Gray-code quadrature: index (prev_state << 2) | new_state -> step delta
_QUAD_DELTA = (
    0,
    -1,
    1,
    0,
    1,
    0,
    0,
    -1,
    -1,
    0,
    0,
    1,
    0,
    1,
    -1,
    0,
)


@dataclass(frozen=True)
class EncoderMapping:
    clk: int = 17
    dt: int = 27
    sw: int = 22


class QuadratureDecoder:
    """Decode CLK/DT transitions into detent steps (testable without GPIO)."""

    def __init__(self, steps_per_detent: int = 4) -> None:
        self.steps_per_detent = max(1, steps_per_detent)
        self._last_ab = 0
        self._accumulator = 0

    def reset(self) -> None:
        self._last_ab = 0
        self._accumulator = 0

    def update(self, clk: int, dt: int) -> tuple[int, int]:
        """Return (cw_detents, ccw_detents) since the last update."""
        ab = ((clk & 1) << 1) | (dt & 1)
        index = (self._last_ab << 2) | ab
        self._last_ab = ab
        self._accumulator += _QUAD_DELTA[index]

        cw = 0
        ccw = 0
        while self._accumulator >= self.steps_per_detent:
            self._accumulator -= self.steps_per_detent
            cw += 1
        while self._accumulator <= -self.steps_per_detent:
            self._accumulator += self.steps_per_detent
            ccw += 1
        return cw, ccw


class RotaryEncoder:
    """KY-040 on Raspberry Pi GPIO via lgpio."""

    def __init__(
        self,
        mapping: EncoderMapping | None = None,
        *,
        steps_per_detent: int = 4,
        sw_debounce_seconds: float = 0.03,
    ) -> None:
        self.mapping = mapping or EncoderMapping()
        self.sw_debounce_seconds = sw_debounce_seconds
        self._decoder = QuadratureDecoder(steps_per_detent)
        self._chip: int | None = None
        self._last_sw = 1
        self._last_select = 0.0

    def open(self) -> None:
        if lgpio is None:
            raise RuntimeError(
                "python3-lgpio is required for the rotary encoder. "
                "Install with: sudo apt install python3-lgpio && "
                "recreate venv: sudo python3 -m venv --system-site-packages /opt/ndp/venv"
            )

        for pin in (self.mapping.clk, self.mapping.dt, self.mapping.sw):
            subprocess.run(
                ["pinctrl", "set", str(pin), "pu"],
                check=False,
                capture_output=True,
            )

        self._chip = lgpio.gpiochip_open(0)
        for pin in (self.mapping.clk, self.mapping.dt, self.mapping.sw):
            lgpio.gpio_claim_input(self._chip, pin, lgpio.SET_PULL_UP)

        clk = lgpio.gpio_read(self._chip, self.mapping.clk)
        dt = lgpio.gpio_read(self._chip, self.mapping.dt)
        self._decoder.reset()
        self._decoder.update(clk, dt)
        self._last_sw = lgpio.gpio_read(self._chip, self.mapping.sw)

        logger.info(
            "Encoder ready CLK=%s DT=%s SW=%s (steps/detent=%s)",
            self.mapping.clk,
            self.mapping.dt,
            self.mapping.sw,
            self._decoder.steps_per_detent,
        )

    def close(self) -> None:
        if self._chip is not None:
            lgpio.gpiochip_close(self._chip)
            self._chip = None

    def poll(self, handler: Callable[[ButtonAction], None]) -> None:
        if self._chip is None:
            return

        clk = lgpio.gpio_read(self._chip, self.mapping.clk)
        dt = lgpio.gpio_read(self._chip, self.mapping.dt)
        cw, ccw = self._decoder.update(clk, dt)
        for _ in range(cw):
            handler(ButtonAction.NEXT)
        for _ in range(ccw):
            handler(ButtonAction.PREVIOUS)

        sw = lgpio.gpio_read(self._chip, self.mapping.sw)
        previous_sw = self._last_sw
        self._last_sw = sw
        if previous_sw == 1 and sw == 0:
            now = time.monotonic()
            if now - self._last_select >= self.sw_debounce_seconds:
                self._last_select = now
                handler(ButtonAction.SELECT)

    def __enter__(self) -> RotaryEncoder:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
