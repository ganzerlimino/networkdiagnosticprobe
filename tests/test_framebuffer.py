from ndp.ui.framebuffer import FramebufferFormat, rgb_to_pixel, solid_fill_bytes


def test_rgb_to_pixel_standard_rgb565() -> None:
    fmt = FramebufferFormat(
        width=320,
        height=240,
        bpp=16,
        line_length=640,
        xoffset=0,
        yoffset=0,
        red_offset=11,
        red_length=5,
        green_offset=5,
        green_length=6,
        blue_offset=0,
        blue_length=5,
    )
    assert rgb_to_pixel(255, 0, 0, fmt) == 0xF800
    assert rgb_to_pixel(0, 255, 0, fmt) == 0x07E0
    assert rgb_to_pixel(0, 0, 255, fmt) == 0x001F


def test_solid_fill_bytes_size() -> None:
    fmt = FramebufferFormat(
        width=4,
        height=2,
        bpp=16,
        line_length=8,
        xoffset=0,
        yoffset=0,
        red_offset=11,
        red_length=5,
        green_offset=5,
        green_length=6,
        blue_offset=0,
        blue_length=5,
    )
    data = solid_fill_bytes(fmt, 255, 0, 0)
    assert len(data) == 16
    assert data[0] == 0x00 and data[1] == 0xF8
