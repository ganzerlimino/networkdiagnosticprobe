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
        *,
        debounce_seconds: float = 0.05,
        trigger_mode: str = "level",
        press_confirm_ms: int = 0,
    ) -> None:
        self.mapping = mapping or ButtonMapping()
        self.debounce_seconds = debounce_seconds
        self.trigger_mode = trigger_mode if trigger_mode in {"level", "edge"} else "level"
        self.press_confirm_ms = max(0, press_confirm_ms)
        self._chip: int | None = None
        self._last_fire: dict[ButtonAction, float] = {}
        self._pin_to_action = {
            self.mapping.previous: ButtonAction.PREVIOUS,
            self.mapping.select: ButtonAction.SELECT,
            self.mapping.next: ButtonAction.NEXT,
        }
        self._last_levels: dict[int, int] = {}
        self._press_started: dict[int, float] = {}
        self._armed: dict[int, bool] = {pin: True for pin in self._pin_to_action}

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
            "Buttons ready on GPIO %s/%s/%s (mode=%s, confirm=%sms)",
            self.mapping.previous,
            self.mapping.select,
            self.mapping.next,
            self.trigger_mode,
            self.press_confirm_ms,
        )

    def close(self) -> None:
        if self._chip is not None:
            lgpio.gpiochip_close(self._chip)
            self._chip = None

    def poll(self, handler: Callable[[ButtonAction], None]) -> None:
        if self._chip is None:
            return

        now = time.monotonic()
        confirm_seconds = self.press_confirm_ms / 1000.0

        for pin, action in self._pin_to_action.items():
            level = lgpio.gpio_read(self._chip, pin)
            previous = self._last_levels.get(pin)
            self._last_levels[pin] = level

            if self.trigger_mode == "edge":
                self._poll_edge(pin, action, level, previous, now, handler)
            else:
                self._poll_level(pin, action, level, now, confirm_seconds, handler)

    def _poll_edge(
        self,
        pin: int,
        action: ButtonAction,
        level: int,
        previous: int | None,
        now: float,
        handler: Callable[[ButtonAction], None],
    ) -> None:
        if previous is None or level == previous or level != 0:
            return
        last = self._last_fire.get(action, 0.0)
        if now - last < self.debounce_seconds:
            return
        self._last_fire[action] = now
        handler(action)

    def _poll_level(
        self,
        pin: int,
        action: ButtonAction,
        level: int,
        now: float,
        confirm_seconds: float,
        handler: Callable[[ButtonAction], None],
    ) -> None:
        pressed = level == 0
        if pressed:
            if pin not in self._press_started:
                self._press_started[pin] = now
            held = now - self._press_started[pin]
            if (
                held >= confirm_seconds
                and self._armed.get(pin, True)
                and now - self._last_fire.get(action, 0.0) >= self.debounce_seconds
            ):
                self._last_fire[action] = now
                self._armed[pin] = False
                handler(action)
            return

        self._press_started.pop(pin, None)
        self._armed[pin] = True

    def __enter__(self) -> PhysicalButtons:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
