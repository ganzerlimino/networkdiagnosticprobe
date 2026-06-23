from ndp.ui.framebuffer import RED, rgb888_to_rgb565, solid_rgb565_bytes, surface_to_rgb565_bytes


def test_rgb888_to_rgb565_white() -> None:
    assert rgb888_to_rgb565(255, 255, 255) == 0xFFFF


def test_rgb888_to_rgb565_black() -> None:
    assert rgb888_to_rgb565(0, 0, 0) == 0x0000


def test_surface_to_rgb565_bytes_size() -> None:
    import os

    import pygame

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    surface = pygame.Surface((4, 2))
    surface.fill((255, 0, 0))
    data = surface_to_rgb565_bytes(surface, line_length=8, bgr=False, swap_bytes=False)
    assert len(data) == 16
    assert data[0] == 0x00 and data[1] == 0xF8  # red RGB565 LE
    pygame.quit()


def test_solid_rgb565_bytes() -> None:
    data = solid_rgb565_bytes(2, 2, 4, RED)
    assert len(data) == 8
    assert data[0] == 0x00 and data[1] == 0xF8
