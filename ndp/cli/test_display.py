"""Display diagnostics for TFT framebuffer bring-up."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from argparse import Namespace
from pathlib import Path

from ndp.core.config import load_config
from ndp.ui.backlight import enable_backlight
from ndp.ui.framebuffer import RawFramebuffer

logger = logging.getLogger(__name__)

COLOR_MAP = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
}


def add_test_subparser(subparsers) -> None:
    test = subparsers.add_parser("test", help="Hardware diagnostic tests")
    test_sub = test.add_subparsers(dest="test_command", required=True)

    display = test_sub.add_parser("display", help="Fill TFT with solid test colors")
    display.add_argument(
        "--device",
        help="Framebuffer device (default: from config or /dev/fb1)",
    )
    display.add_argument(
        "--color",
        choices=sorted(COLOR_MAP.keys()) + ["cycle"],
        default="cycle",
        help="Fill color (default: cycle through colors)",
    )
    display.add_argument(
        "--seconds",
        type=float,
        default=3.0,
        help="Seconds per color (default: 3)",
    )
    display.add_argument(
        "--no-backlight",
        action="store_true",
        help="Do not drive GPIO18 backlight",
    )
    display.add_argument(
        "--via-fbi",
        action="store_true",
        help="Render via temporary PNG + fbi (diagnostic fallback)",
    )


def run_test_command(args: Namespace, config_path) -> int:
    if args.test_command != "display":
        return 1

    config = load_config(config_path)
    device = args.device or config.ui_framebuffer
    backlight_pin = config.ui_backlight_gpio

    if not args.no_backlight:
        enable_backlight(backlight_pin)

    colors = (
        list(COLOR_MAP.items())
        if args.color == "cycle"
        else [(args.color, COLOR_MAP[args.color])]
    )

    print(f"Testing {device} ({len(colors)} color step(s), {args.seconds}s each)")

    if args.via_fbi:
        return _test_via_fbi(device, colors, args.seconds)

    with RawFramebuffer(device, config.ui_width, config.ui_height) as fb:
        print(
            f"Framebuffer {fb.width}x{fb.height}, "
            f"stride={fb.line_length}, bpp={fb.bpp}"
        )
        print(f"Kernel format: {fb.format.describe()}")
        for name, rgb in colors:
            print(f"  -> {name} RGB{rgb}")
            fb.fill_rgb(*rgb)
            time.sleep(args.seconds)

    print("Done.")
    return 0


def _test_via_fbi(device: str, colors: list[tuple[str, tuple[int, int, int]]], seconds: float) -> int:
    import pygame

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    surface = pygame.Surface((320, 240))

    with tempfile.TemporaryDirectory(prefix="ndp-fbi-") as tmp:
        for name, rgb in colors:
            path = Path(tmp) / f"{name}.png"
            surface.fill(rgb)
            pygame.image.save(surface, path)
            print(f"  -> {name} via fbi ({path})")
            subprocess.run(
                ["fbi", "-d", device, "-T", "1", "-noverbose", "-a", str(path)],
                check=False,
            )
            time.sleep(seconds)

    pygame.quit()
    return 0
