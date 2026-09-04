"""Direct Linux framebuffer output (for Pi OS Lite without SDL fbcon)."""

from __future__ import annotations

import ctypes
import fcntl
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FBIOGET_FSCREENINFO = 0x4602
FBIOGET_VSCREENINFO = 0x4600


class FbBitField(ctypes.Structure):
    _fields_ = [
        ("offset", ctypes.c_uint32),
        ("length", ctypes.c_uint32),
        ("msb_right", ctypes.c_uint32),
    ]


class FbVarScreenInfo(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_uint32),
        ("yres", ctypes.c_uint32),
        ("xres_virtual", ctypes.c_uint32),
        ("yres_virtual", ctypes.c_uint32),
        ("xres_offset", ctypes.c_uint32),
        ("yres_offset", ctypes.c_uint32),
        ("bits_per_pixel", ctypes.c_uint32),
        ("grayscale", ctypes.c_uint32),
        ("red", FbBitField),
        ("green", FbBitField),
        ("blue", FbBitField),
        ("transp", FbBitField),
    ]


class FbFixScreenInfo(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_char * 16),
        ("smem_start", ctypes.c_ulong),
        ("smem_len", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("type_aux", ctypes.c_uint32),
        ("visual", ctypes.c_uint32),
        ("xpanstep", ctypes.c_uint16),
        ("ypanstep", ctypes.c_uint16),
        ("ywrapstep", ctypes.c_uint16),
        ("line_length", ctypes.c_uint32),
    ]


@dataclass
class FramebufferFormat:
    width: int
    height: int
    bpp: int
    line_length: int
    xoffset: int
    yoffset: int
    red_offset: int
    red_length: int
    green_offset: int
    green_length: int
    blue_offset: int
    blue_length: int

    @classmethod
    def from_ioctl(cls, var: FbVarScreenInfo, fix: FbFixScreenInfo) -> FramebufferFormat:
        return cls(
            width=var.xres,
            height=var.yres,
            bpp=var.bits_per_pixel,
            line_length=fix.line_length or (var.xres * var.bits_per_pixel // 8),
            xoffset=var.xres_offset,
            yoffset=var.yres_offset,
            red_offset=var.red.offset,
            red_length=var.red.length,
            green_offset=var.green.offset,
            green_length=var.green.length,
            blue_offset=var.blue.offset,
            blue_length=var.blue.length,
        )

    def describe(self) -> str:
        return (
            f"{self.width}x{self.height} bpp={self.bpp} stride={self.line_length} "
            f"R({self.red_offset},{self.red_length}) "
            f"G({self.green_offset},{self.green_length}) "
            f"B({self.blue_offset},{self.blue_length})"
        )


def rgb_to_pixel(r: int, g: int, b: int, fmt: FramebufferFormat) -> int:
    def channel(value: int, offset: int, length: int) -> int:
        if length <= 0:
            return 0
        max_val = (1 << length) - 1
        scaled = (value * max_val + 127) // 255
        return (scaled & max_val) << offset

    return (
        channel(r, fmt.red_offset, fmt.red_length)
        | channel(g, fmt.green_offset, fmt.green_length)
        | channel(b, fmt.blue_offset, fmt.blue_length)
    )


def surface_to_framebuffer_bytes(surface, fmt: FramebufferFormat) -> bytes:
    import pygame

    width, height = surface.get_size()
    stride = fmt.line_length
    out = bytearray(stride * fmt.height)
    rgb = pygame.image.tobytes(surface, "RGB")

    for y in range(min(height, fmt.height)):
        row_offset = y * stride
        row_rgb = y * width * 3
        for x in range(min(width, fmt.width)):
            index = row_rgb + x * 3
            red, green, blue = rgb[index], rgb[index + 1], rgb[index + 2]
            pixel = rgb_to_pixel(red, green, blue, fmt)
            pixel_offset = row_offset + (x * fmt.bpp // 8)
            if fmt.bpp == 16:
                out[pixel_offset] = pixel & 0xFF
                out[pixel_offset + 1] = (pixel >> 8) & 0xFF
            elif fmt.bpp == 32:
                out[pixel_offset] = pixel & 0xFF
                out[pixel_offset + 1] = (pixel >> 8) & 0xFF
                out[pixel_offset + 2] = (pixel >> 16) & 0xFF
                out[pixel_offset + 3] = (pixel >> 24) & 0xFF

    return bytes(out)


def solid_fill_bytes(fmt: FramebufferFormat, r: int, g: int, b: int) -> bytes:
    pixel = rgb_to_pixel(r, g, b, fmt)
    bytes_per_pixel = max(1, fmt.bpp // 8)
    pixel_bytes = pixel.to_bytes(bytes_per_pixel, byteorder="little", signed=False)
    row = pixel_bytes * fmt.width
    if len(row) < fmt.line_length:
        row += b"\x00" * (fmt.line_length - len(row))
    return row * fmt.height


class RawFramebuffer:
    """Framebuffer writer using os.write().

    On Joy-it / fbtft devices mmap updates may not reach the panel; the kernel
  fb_write path (used by fbi and plain file writes) does.
    """

    def __init__(self, device: str, width: int, height: int) -> None:
        self.device = device
        self._fd = os.open(device, os.O_RDWR)

        var = FbVarScreenInfo()
        fix = FbFixScreenInfo()
        fcntl.ioctl(self._fd, FBIOGET_VSCREENINFO, var)
        fcntl.ioctl(self._fd, FBIOGET_FSCREENINFO, fix)

        if var.xres == 0:
            var.xres = width
        if var.yres == 0:
            var.yres = height

        self.format = FramebufferFormat.from_ioctl(var, fix)
        logger.info("Framebuffer format: %s", self.format.describe())

        if self.format.bpp not in (16, 32):
            raise RuntimeError(
                f"{device} uses {self.format.bpp} bpp; NDP UI supports 16/32-bit only"
            )

        self._base_offset = (self.format.yoffset * self.format.line_length) + (
            self.format.xoffset * self.format.bpp // 8
        )

    @property
    def width(self) -> int:
        return self.format.width

    @property
    def height(self) -> int:
        return self.format.height

    @property
    def line_length(self) -> int:
        return self.format.line_length

    @property
    def bpp(self) -> int:
        return self.format.bpp

    def blit_surface(self, surface) -> None:
        data = surface_to_framebuffer_bytes(surface, self.format)
        self._write(data)

    def fill_rgb(self, r: int, g: int, b: int) -> None:
        data = solid_fill_bytes(self.format, r, g, b)
        self._write(data)

    def _write(self, data: bytes) -> None:
        os.lseek(self._fd, self._base_offset, os.SEEK_SET)
        written = 0
        while written < len(data):
            chunk = os.write(self._fd, data[written:])
            if chunk <= 0:
                raise OSError(f"short write to {self.device} at offset {written}")
            written += chunk

    def close(self) -> None:
        if hasattr(self, "_fd"):
            os.close(self._fd)
            del self._fd

    def __enter__(self) -> RawFramebuffer:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
