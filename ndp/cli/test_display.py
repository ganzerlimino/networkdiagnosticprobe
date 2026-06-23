"""Display diagnostics for TFT framebuffer bring-up."""

from __future__ import annotations

import logging
import time
from argparse import Namespace

from ndp.core.config import load_config
from ndp.ui.backlight import enable_backlight
from ndp.ui.framebuffer import BLUE, GREEN, RED, WHITE, RawFramebuffer

logger = logging.getLogger(__name__)

COLOR_MAP = {
    "red": RED,
    "green": GREEN,
    "blue": BLUE,
    "white": WHITE,
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
        "--swap-bytes",
        action="store_true",
        help="Swap RGB565 byte order",
    )
    display.add_argument(
        "--bgr",
        action="store_true",
        help="Use BGR565 component order",
    )
    display.add_argument(
        "--no-backlight",
        action="store_true",
        help="Do not drive GPIO18 backlight",
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
    with RawFramebuffer(
        device,
        config.ui_width,
        config.ui_height,
        bgr=args.bgr,
        swap_bytes=args.swap_bytes,
    ) as fb:
        print(
            f"Framebuffer {fb.width}x{fb.height}, "
            f"stride={fb.line_length}, bpp={fb.bpp}"
        )
        for name, value in colors:
            print(f"  -> {name} (0x{value:04X})")
            fb.fill_color(value)
            time.sleep(args.seconds)

    print("Done. If the TFT stayed black, try:")
    print("  ndp test display --swap-bytes")
    print("  ndp test display --bgr")
    print("  ndp test display --swap-bytes --bgr")
    return 0
