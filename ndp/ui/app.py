"""Pygame framebuffer UI for NDP."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

from ndp.core.config import NdpConfig
from ndp.core.engine import ProbeEngine
from ndp.core.state import ProbeState
from ndp.ui.buttons import ButtonAction, ButtonMapping, PhysicalButtons
from ndp.ui.framebuffer import RawFramebuffer
from ndp.ui.screens import ScreenId, lines_for_screen, next_screen

if TYPE_CHECKING:
    import pygame

logger = logging.getLogger(__name__)

COLOR_BG = (12, 18, 32)
COLOR_HEADER = (24, 36, 64)
COLOR_TEXT = (235, 240, 255)
COLOR_MUTED = (140, 155, 180)
COLOR_ACCENT = (80, 200, 120)


def _configure_pygame_env(config: NdpConfig, use_dummy: bool) -> None:
    driver = "dummy" if use_dummy else config.ui_sdl_driver
    os.environ["SDL_VIDEODRIVER"] = driver
    os.environ["SDL_FBDEV"] = config.ui_framebuffer
    os.environ["SDL_MOUSE"] = "0"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"


def _load_font(size: int) -> pygame.font.Font:
    import pygame

    for name in ("dejavusans", "dejavusansmono", "liberationsans", "freesans"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def _init_display(config: NdpConfig) -> tuple[pygame.Surface, RawFramebuffer | None]:
    """Return pygame surface and optional raw framebuffer for blitting."""
    import pygame

    errors: list[str] = []

    if config.ui_backend != "raw":
        _configure_pygame_env(config, use_dummy=False)
        try:
            if pygame.get_init():
                pygame.quit()
            pygame.init()
            pygame.font.init()
            screen = pygame.display.set_mode(
                (config.ui_width, config.ui_height),
                pygame.FULLSCREEN,
            )
            pygame.mouse.set_visible(False)
            logger.info("UI using SDL driver %s", os.environ.get("SDL_VIDEODRIVER"))
            return screen, None
        except pygame.error as exc:
            errors.append(f"sdl:{exc}")
            pygame.quit()

    _configure_pygame_env(config, use_dummy=True)
    if pygame.get_init():
        pygame.quit()
    pygame.init()
    pygame.font.init()
    surface = pygame.Surface((config.ui_width, config.ui_height))
    raw_fb = RawFramebuffer(config.ui_framebuffer, config.ui_width, config.ui_height)
    logger.info(
        "UI using offscreen pygame + raw framebuffer %s (%sx%s, stride=%s)",
        config.ui_framebuffer,
        raw_fb.width,
        raw_fb.height,
        raw_fb.line_length,
    )
    if errors:
        logger.warning("SDL display unavailable (%s); raw fallback active", "; ".join(errors))
    return surface, raw_fb


class ProbeUI:
    def __init__(self, config: NdpConfig) -> None:
        self.config = config
        self.engine = ProbeEngine(config)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._force_refresh = threading.Event()
        self._screen = ScreenId.HOME
        self._state = ProbeState(interface=config.interface)
        self._buttons = PhysicalButtons(
            ButtonMapping(
                previous=config.ui_button_previous,
                select=config.ui_button_select,
                next=config.ui_button_next,
            ),
            debounce_seconds=config.ui_button_debounce_seconds,
        )

    def _engine_loop(self) -> None:
        while not self._stop.is_set():
            if self._force_refresh.is_set():
                self._force_refresh.clear()
            with self._lock:
                self._state = self.engine.refresh()
            time.sleep(self.engine.poll_interval())

    def _on_button(self, action: ButtonAction) -> None:
        if action == ButtonAction.PREVIOUS:
            self._screen = next_screen(self._screen, -1)
        elif action == ButtonAction.NEXT:
            self._screen = next_screen(self._screen, 1)
        elif action == ButtonAction.SELECT:
            self._force_refresh.set()
            with self._lock:
                self._state = self.engine.refresh()

    def run(self) -> int:
        import pygame

        screen, raw_fb = _init_display(self.config)

        title_font = _load_font(self.config.ui_font_size + 4)
        body_font = _load_font(self.config.ui_font_size)
        hint_font = _load_font(max(12, self.config.ui_font_size - 2))

        worker = threading.Thread(target=self._engine_loop, daemon=True)
        worker.start()

        try:
            with self._buttons:
                clock = pygame.time.Clock()
                while not self._stop.is_set():
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            self._stop.set()

                    self._buttons.poll(self._on_button)

                    with self._lock:
                        state = self._state
                        current = self._screen

                    self._draw(screen, title_font, body_font, hint_font, current, state)

                    if raw_fb is not None:
                        raw_fb.blit_surface(screen)
                    else:
                        pygame.display.flip()

                    clock.tick(self.config.ui_fps)
        finally:
            if raw_fb is not None:
                raw_fb.close()
            pygame.quit()

        return 0

    def stop(self) -> None:
        self._stop.set()

    def _draw(
        self,
        surface: pygame.Surface,
        title_font: pygame.font.Font,
        body_font: pygame.font.Font,
        hint_font: pygame.font.Font,
        screen_id: ScreenId,
        state: ProbeState,
    ) -> None:
        import pygame

        surface.fill(COLOR_BG)
        header = pygame.Rect(0, 0, self.config.ui_width, 34)
        pygame.draw.rect(surface, COLOR_HEADER, header)

        title = title_font.render(screen_id.name, True, COLOR_ACCENT)
        surface.blit(title, (10, 6))

        dots = self._screen_dots(screen_id)
        dots_surface = hint_font.render(dots, True, COLOR_MUTED)
        surface.blit(dots_surface, (self.config.ui_width - dots_surface.get_width() - 8, 10))

        y = 42
        for line in lines_for_screen(screen_id, state):
            rendered = body_font.render(line, True, COLOR_TEXT)
            surface.blit(rendered, (10, y))
            y += self.config.ui_font_size + 6

        hint = hint_font.render("< 23    O 24    25 >", True, COLOR_MUTED)
        surface.blit(hint, (10, self.config.ui_height - hint.get_height() - 6))

    def _screen_dots(self, active: ScreenId) -> str:
        parts = []
        for screen in ScreenId:
            parts.append("*" if screen == active else "-")
        return " ".join(parts)


def run_ui(config: NdpConfig) -> int:
    import signal

    ui = ProbeUI(config)

    def _handle_signal(_signum: int, _frame: object) -> None:
        logger.info("UI shutdown requested")
        ui.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    return ui.run()
