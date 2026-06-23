"""Physical button input via lgpio (Joy-it RB-TFT3.2-V3)."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

logger = logging.getLogger(__name__)

try:
    import lgpio
except ImportError:  # pragma: no cover - optional on dev machines
    lgpio = None  # type: ignore[assignment]


class ButtonAction(Enum):
    PREVIOUS = auto()
    SELECT = auto()
    NEXT = auto()


@dataclass(frozen=True)
class ButtonMapping:
    previous: int = 23
    select: int = 24
    next: int = 25


class PhysicalButtons:
    def __init__(
        self,
        mapping: ButtonMapping | None = None,
        debounce_seconds: float = 0.2,
    ) -> None:
        self.mapping = mapping or ButtonMapping()
        self.debounce_seconds = debounce_seconds
        self._chip: int | None = None
        self._last_fire: dict[ButtonAction, float] = {}
        self._pin_to_action = {
            self.mapping.previous: ButtonAction.PREVIOUS,
            self.mapping.select: ButtonAction.SELECT,
            self.mapping.next: ButtonAction.NEXT,
        }
        self._last_levels: dict[int, int] = {}

    def open(self) -> None:
        if lgpio is None:
            raise RuntimeError(
                "python3-lgpio is required for physical buttons. "
                "Install with: sudo apt install python3-lgpio && "
                "recreate venv: sudo python3 -m venv --system-site-packages /opt/ndp/venv"
            )

        for pin in self._pin_to_action:
            subprocess.run(
                ["pinctrl", "set", str(pin), "pu"],
                check=False,
                capture_output=True,
            )

        self._chip = lgpio.gpiochip_open(0)
        for pin in self._pin_to_action:
            lgpio.gpio_claim_input(self._chip, pin, lgpio.SET_PULL_UP)
            self._last_levels[pin] = lgpio.gpio_read(self._chip, pin)

        logger.info(
            "Buttons ready on GPIO %s/%s/%s",
            self.mapping.previous,
            self.mapping.select,
            self.mapping.next,
        )

    def close(self) -> None:
        if self._chip is not None:
            lgpio.gpiochip_close(self._chip)
            self._chip = None

    def poll(self, handler: Callable[[ButtonAction], None]) -> None:
        if self._chip is None:
            return

        now = time.monotonic()
        for pin, action in self._pin_to_action.items():
            level = lgpio.gpio_read(self._chip, pin)
            previous = self._last_levels.get(pin)
            self._last_levels[pin] = level

            if previous is None or level == previous:
                continue
            if level != 0:
                continue

            last = self._last_fire.get(action, 0.0)
            if now - last < self.debounce_seconds:
                continue

            self._last_fire[action] = now
            handler(action)

    def __enter__(self) -> PhysicalButtons:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
