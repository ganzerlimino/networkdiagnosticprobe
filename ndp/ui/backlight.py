"""TFT backlight control (Joy-it RB-TFT3.2-V3 uses GPIO 18)."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

try:
    import lgpio
except ImportError:  # pragma: no cover
    lgpio = None  # type: ignore[assignment]


def enable_backlight(pin: int = 18) -> bool:
    """Turn on display backlight. Returns True if the pin was configured."""
    if pin <= 0:
        return False

    try:
        subprocess.run(
            ["pinctrl", "set", str(pin), "op", "dh"],
            check=False,
            capture_output=True,
        )
        logger.info("Backlight enabled on GPIO %s (pinctrl)", pin)
        return True
    except OSError:
        pass

    if lgpio is None:
        logger.warning("Could not enable backlight on GPIO %s (no lgpio)", pin)
        return False

    try:
        chip = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(chip, pin, 1)
        lgpio.gpio_write(chip, pin, 1)
        lgpio.gpiochip_close(chip)
        logger.info("Backlight enabled on GPIO %s (lgpio)", pin)
        return True
    except lgpio.error as exc:
        logger.warning("Backlight GPIO %s unavailable: %s", pin, exc)
        return False
