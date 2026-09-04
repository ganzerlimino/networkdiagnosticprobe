"""Startup splash screen for the TFT UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ndp.core.config import NdpConfig

if TYPE_CHECKING:
    import pygame

COLOR_BG = (12, 18, 32)
COLOR_ACCENT = (80, 200, 120)
COLOR_MUTED = (140, 155, 180)


def draw_splash(
    surface: pygame.Surface,
    config: NdpConfig,
    *,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    version: str,
    status_line: str,
) -> None:
    from ndp.locale.loader import tft_palette

    palette = tft_palette(config.ui_theme)
    surface.fill(palette["bg"])

    title = title_font.render(config.ui_splash_message, True, palette["accent"])
    title_x = (config.ui_width - title.get_width()) // 2
    surface.blit(title, (title_x, config.ui_height // 2 - 36))

    version_surface = body_font.render(f"v{version}", True, palette["muted"])
    version_x = (config.ui_width - version_surface.get_width()) // 2
    surface.blit(version_surface, (version_x, config.ui_height // 2 - 8))

    status = body_font.render(status_line, True, palette["muted"])
    status_x = (config.ui_width - status.get_width()) // 2
    surface.blit(status, (status_x, config.ui_height // 2 + 24))
