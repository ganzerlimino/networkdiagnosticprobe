"""Layout helpers for the TFT UI (Joy-it RB-TFT3.2-V3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pygame


def content_width(screen_width: int, hint_edge: str, margin: int) -> int:
    if hint_edge in {"right", "left"}:
        return screen_width - margin
    return screen_width


def draw_button_hints(
    surface: pygame.Surface,
    font: pygame.font.Font,
    *,
    edge: str,
    width: int,
    height: int,
    color: tuple[int, int, int],
    margin: int = 48,
) -> None:
    """Draw button legend aligned with the physical side buttons."""
    labels = [
        ("◀", "23"),
        ("○", "24"),
        ("▶", "25"),
    ]

    if edge == "right":
        x_icon = width - margin + 8
        y_positions = (52, height // 2 - 10, height - 72)
        for (icon, gpio), y in zip(labels, y_positions):
            icon_surface = font.render(icon, True, color)
            gpio_surface = font.render(gpio, True, color)
            surface.blit(icon_surface, (x_icon, y))
            surface.blit(gpio_surface, (x_icon + 18, y + 2))
        return

    if edge == "left":
        x_icon = 8
        y_positions = (52, height // 2 - 10, height - 72)
        for (icon, gpio), y in zip(labels, y_positions):
            icon_surface = font.render(icon, True, color)
            gpio_surface = font.render(gpio, True, color)
            surface.blit(icon_surface, (x_icon, y))
            surface.blit(gpio_surface, (x_icon + 18, y + 2))
        return

    # bottom (legacy)
    hint = font.render("< 23    O 24    25 >", True, color)
    surface.blit(hint, (10, height - hint.get_height() - 6))
