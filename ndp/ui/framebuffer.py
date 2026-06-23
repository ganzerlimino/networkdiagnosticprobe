"""Direct Linux framebuffer output (for Pi OS Lite without SDL fbcon)."""

from __future__ import annotations

import fcntl
import mmap
import os
import struct
from pathlib import Path

FBIOGET_FSCREENINFO = 0x4602
FBIOGET_VSCREENINFO = 0x4600

# RGB565 color constants
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
WHITE = 0xFFFF
BLACK = 0x0000


def rgb888_to_rgb565(r: int, g: int, b: int, *, bgr: bool = False) -> int:
    if bgr:
        r, b = b, r
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def _pack_pixel(value: int, *, swap_bytes: bool) -> tuple[int, int]:
    if swap_bytes:
        return (value >> 8) & 0xFF, value & 0xFF
    return value & 0xFF, (value >> 8) & 0xFF


def surface_to_rgb565_bytes(
    surface,
    line_length: int | None = None,
    *,
    bgr: bool = False,
    swap_bytes: bool = False,
) -> bytes:
    """Convert a pygame Surface to RGB565 framebuffer bytes."""
    import pygame

    width, height = surface.get_size()
    stride = line_length or (width * 2)
    out = bytearray(stride * height)
    rgb = pygame.image.tobytes(surface, "RGB")

    for y in range(height):
        row_offset = y * stride
        row_rgb = y * width * 3
        for x in range(width):
            index = row_rgb + x * 3
            red, green, blue = rgb[index], rgb[index + 1], rgb[index + 2]
            value = rgb888_to_rgb565(red, green, blue, bgr=bgr)
            low, high = _pack_pixel(value, swap_bytes=swap_bytes)
            pixel_offset = row_offset + (x * 2)
            out[pixel_offset] = low
            out[pixel_offset + 1] = high

    return bytes(out)


def solid_rgb565_bytes(
    width: int,
    height: int,
    line_length: int,
    color: int,
    *,
    swap_bytes: bool = False,
) -> bytes:
    low, high = _pack_pixel(color, swap_bytes=swap_bytes)
    pixel = bytes((low, high))
    row = pixel * width
    if len(row) < line_length:
        row += b"\x00" * (line_length - len(row))
    return row * height


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


def _read_line_length(sys_base: Path, width: int, fix: bytearray) -> int:
    for path in (sys_base / "stride", sys_base / "line_length"):
        value = _read_sysfs_int(path, 0)
        if value > 0:
            return value

    for offset in (48, 32, 36):
        try:
            value = struct.unpack_from("I", fix, offset)[0]
        except struct.error:
            continue
        if value >= width * 2:
            return value
    return width * 2


class RawFramebuffer:
    """Memory-mapped write access to /dev/fbX."""

    def __init__(
        self,
        device: str,
        width: int,
        height: int,
        *,
        bgr: bool = False,
        swap_bytes: bool = False,
    ) -> None:
        self.device = device
        self.width = width
        self.height = height
        self.bgr = bgr
        self.swap_bytes = swap_bytes
        self.line_length = width * 2
        self.bpp = 16

        fb_idx = _fb_index(device)
        sys_base = Path(f"/sys/class/graphics/fb{fb_idx}")
        self.bpp = _read_sysfs_int(sys_base / "bits_per_pixel", 16)

        self._fd = os.open(device, os.O_RDWR)
        try:
            fix = bytearray(128)
            fcntl.ioctl(self._fd, FBIOGET_FSCREENINFO, fix)
            self.line_length = _read_line_length(sys_base, width, fix)

            var = bytearray(160)
            fcntl.ioctl(self._fd, FBIOGET_VSCREENINFO, var)
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
                f"{device} uses {self.bpp} bpp; NDP UI supports 16-bit RGB565 only"
            )

        size = self.line_length * self.height
        self._mmap = mmap.mmap(self._fd, size, mmap.MAP_SHARED, mmap.PROT_WRITE)

    def blit_surface(self, surface) -> None:
        data = surface_to_rgb565_bytes(
            surface,
            self.line_length,
            bgr=self.bgr,
            swap_bytes=self.swap_bytes,
        )
        self._write(data)

    def fill_color(self, color: int) -> None:
        data = solid_rgb565_bytes(
            self.width,
            self.height,
            self.line_length,
            color,
            swap_bytes=self.swap_bytes,
        )
        self._write(data)

    def _write(self, data: bytes) -> None:
        write_len = min(len(data), self._mmap.size())
        self._mmap.seek(0)
        self._mmap.write(data[:write_len])
        self._mmap.flush()
        os.fsync(self._fd)

    def close(self) -> None:
        if hasattr(self, "_mmap"):
            self._mmap.close()
        if hasattr(self, "_fd"):
            os.close(self._fd)

    def __enter__(self) -> RawFramebuffer:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
