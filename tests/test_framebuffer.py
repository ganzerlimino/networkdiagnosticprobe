from ndp.ui.framebuffer import rgb888_to_rgb565, surface_to_rgb565_bytes


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
    data = surface_to_rgb565_bytes(surface, line_length=8)
    assert len(data) == 16
    pygame.quit()
