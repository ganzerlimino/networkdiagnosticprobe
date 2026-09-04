#!/usr/bin/env python3
"""Log GPIO button presses to a text file (Joy-it RB-TFT3.2-V3: GPIO 23/24/25)."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import lgpio
except ImportError:
    print("Install: sudo apt install -y python3-lgpio", file=sys.stderr)
    sys.exit(1)

DEFAULT_PINS = (23, 24, 25)
DEFAULT_LOG = Path("/home/pi/ndp-button-test.log")


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _enable_pullups(pins: tuple[int, ...]) -> None:
    for pin in pins:
        subprocess.run(
            ["pinctrl", "set", str(pin), "pu"],
            check=False,
            capture_output=True,
        )


def _log_line(log_path: Path, message: str) -> None:
    line = f"{_timestamp()}  {message}\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(line, end="", flush=True)


def run_logger(
    pins: tuple[int, ...],
    log_path: Path,
    poll_interval: float,
    sample_every: float,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    _enable_pullups(pins)
    time.sleep(0.2)

    chip = lgpio.gpiochip_open(0)
    stop = False

    def _handle_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    for pin in pins:
        try:
            lgpio.gpio_claim_input(chip, pin, lgpio.SET_PULL_UP)
        except lgpio.error as exc:
            _log_line(log_path, f"GPIO{pin} ERROR claim: {exc}")

    _log_line(log_path, f"START logger pins={pins} log={log_path}")
    _log_line(log_path, "Vai a premere i tasti. Torna dopo e leggi questo file.")

    last_levels: dict[int, int] = {}
    last_sample_at = 0.0

    try:
        while not stop:
            now = time.monotonic()
            for pin in pins:
                try:
                    level = lgpio.gpio_read(chip, pin)
                except lgpio.error:
                    continue

                previous = last_levels.get(pin)
                if previous is not None and level != previous:
                    state = "PRESSED" if level == 0 else "RELEASED"
                    _log_line(log_path, f"GPIO{pin} {state} (level={level})")
                last_levels[pin] = level

            if sample_every > 0 and (now - last_sample_at) >= sample_every:
                snapshot = " ".join(
                    f"GPIO{p}={'LOW' if last_levels.get(p) == 0 else 'HIGH'}"
                    for p in pins
                )
                _log_line(log_path, f"SAMPLE {snapshot}")
                last_sample_at = now

            time.sleep(poll_interval)
    finally:
        _log_line(log_path, "STOP logger")
        lgpio.gpiochip_close(chip)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NDP button press file logger")
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"Log file path (default: {DEFAULT_LOG})",
    )
    parser.add_argument(
        "--pins",
        type=int,
        nargs="+",
        default=list(DEFAULT_PINS),
        help="BCM GPIO pins (default: 23 24 25)",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.05,
        help="Poll interval in seconds (default: 0.05)",
    )
    parser.add_argument(
        "--sample-every",
        type=float,
        default=5.0,
        help="Log full pin snapshot every N seconds (0=disable, default: 5)",
    )
    args = parser.parse_args()
    return run_logger(tuple(args.pins), args.log, args.poll, args.sample_every)


if __name__ == "__main__":
    sys.exit(main())
