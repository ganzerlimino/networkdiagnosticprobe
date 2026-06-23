"""Direct Linux framebuffer output (for Pi OS Lite without SDL fbcon)."""

from __future__ import annotations

import fcntl
import mmap
import os
import struct
from pathlib import Path

FBIOGET_FSCREENINFO = 0x4602
FBIOGET_VSCREENINFO = 0x4600


def rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def surface_to_rgb565_bytes(surface, line_length: int | None = None) -> bytes:
    """Convert a pygame Surface to little-endian RGB565 framebuffer bytes."""
    width, height = surface.get_size()
    stride = line_length or (width * 2)
    out = bytearray(stride * height)

    for y in range(height):
        row_offset = y * stride
        for x in range(width):
            red, green, blue, _alpha = surface.get_at((x, y))
            value = rgb888_to_rgb565(red, green, blue)
            index = row_offset + (x * 2)
            out[index] = value & 0xFF
            out[index + 1] = (value >> 8) & 0xFF

    return bytes(out)


def _fb_index(device: str) -> str:
    name = Path(device).name
    if name.startswith("fb") and name[2:].isdigit():
        return name[2:]
    return "1"


def _read_sysfs_int(path: Path, default: int) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return default


class RawFramebuffer:
    """Memory-mapped write access to /dev/fbX."""

    def __init__(self, device: str, width: int, height: int) -> None:
        self.device = device
        self.width = width
        self.height = height
        self.line_length = width * 2
        self.bpp = 16

        fb_idx = _fb_index(device)
        sys_base = Path(f"/sys/class/graphics/fb{fb_idx}")
        self.bpp = _read_sysfs_int(sys_base / "bits_per_pixel", 16)

        self._fd = os.open(device, os.O_RDWR)
        try:
            fix = bytearray(128)
            fcntl.ioctl(self._fd, FBIOGET_FSCREENINFO, fix)
            # line_length is at byte offset 48 on arm64 fb_fix_screeninfo
            self.line_length = struct.unpack_from("I", fix, 48)[0] or (width * 2)

            var = bytearray(160)
            fcntl.ioctl(self._fd, FBIOGET_VSCREENINFO, var)
            # xres at 0, yres at 4, bits_per_pixel at 24
            xres = struct.unpack_from("I", var, 0)[0] or width
            yres = struct.unpack_from("I", var, 4)[0] or height
            bpp = struct.unpack_from("I", var, 24)[0] or self.bpp
            if xres:
                self.width = xres
            if yres:
                self.height = yres
            if bpp:
                self.bpp = bpp
        except OSError:
            self.line_length = width * 2

        if self.bpp != 16:
            raise RuntimeError(
                f"{device} uses {self.bpp} bpp; NDP UI currently supports 16-bit RGB565 only"
            )

        size = self.line_length * self.height
        self._mmap = mmap.mmap(self._fd, size, mmap.MAP_SHARED, mmap.PROT_WRITE)

    def blit_surface(self, surface) -> None:
        data = surface_to_rgb565_bytes(surface, self.line_length)
        write_len = min(len(data), self._mmap.size())
        self._mmap.seek(0)
        self._mmap.write(data[:write_len])

    def close(self) -> None:
        if hasattr(self, "_mmap"):
            self._mmap.close()
        if hasattr(self, "_fd"):
            os.close(self._fd)

    def __enter__(self) -> RawFramebuffer:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
