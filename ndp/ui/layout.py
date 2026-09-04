"""Layout helpers for the TFT UI (Joy-it RB-TFT3.2-V3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pygame


def content_width(screen_width: int, hint_edge: str, margin: int) -> int:
    if hint_edge in {"right", "left"}:
        return screen_width - margin
    return screen_width


def content_x_offset(hint_edge: str, margin: int) -> int:
    """Horizontal offset for main content when hints sit on the left edge."""
    return margin if hint_edge == "left" else 0


def content_text_x(hint_edge: str, margin: int, text_gap: int) -> int:
    """Left edge of text block (hint column + configurable gap)."""
    return content_x_offset(hint_edge, margin) + text_gap


def hint_y_positions(height: int, y_offset: int) -> tuple[int, int, int]:
    """Vertical positions for prev / select / next side-button hints."""
    return (
        52 + y_offset,
        height // 2 - 10 + y_offset,
        height - 72 + y_offset,
    )


def draw_button_hints(
    surface: pygame.Surface,
    font: pygame.font.Font,
    *,
    edge: str,
    width: int,
    height: int,
    color: tuple[int, int, int],
    margin: int = 32,
    y_offset: int = 24,
) -> None:
    """Draw button legend (icons only) aligned with the physical side buttons."""
    icons = ("◀", "○", "▶")
    y_positions = hint_y_positions(height, y_offset)

    if edge == "none":
        return

    if edge == "right":
        x_icon = width - margin + max(4, (margin - 16) // 2)
        for icon, y in zip(icons, y_positions):
            surface.blit(font.render(icon, True, color), (x_icon, y))
        return

    if edge == "left":
        x_icon = max(4, (margin - 16) // 2)
        for icon, y in zip(icons, y_positions):
            surface.blit(font.render(icon, True, color), (x_icon, y))
        return

    # bottom (legacy)
    hint = font.render("<  ○  >", True, color)
    surface.blit(hint, (10, height - hint.get_height() - 6))
