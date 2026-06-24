"""Pygame framebuffer UI for NDP."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ndp import __version__
from ndp.core.config import NdpConfig
from ndp.core.engine import ProbeEngine
from ndp.core.state import ProbeState
from ndp.ui.backlight import enable_backlight
from ndp.ui.buttons import ButtonAction, ButtonMapping, PhysicalButtons
from ndp.ui.discovery_session import DiscoveryUISession
from ndp.ui.framebuffer import RawFramebuffer
from ndp.ui.layout import content_text_x, content_width, content_x_offset, draw_button_hints
from ndp.ui.screens import ScreenId, lines_for_screen, next_screen
from ndp.ui.splash import draw_splash

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


def _prefer_raw_backend(config: NdpConfig) -> bool:
    if config.ui_backend == "raw":
        return True
    if config.ui_backend == "sdl":
        return False
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        return True
    return Path(config.ui_framebuffer).exists()


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

    if not _prefer_raw_backend(config):
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
    raw_fb = RawFramebuffer(
        config.ui_framebuffer,
        config.ui_width,
        config.ui_height,
    )
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


def _blit_frame(
    screen: pygame.Surface,
    raw_fb: RawFramebuffer | None,
) -> None:
    if raw_fb is not None:
        raw_fb.blit_surface(screen)
    else:
        import pygame

        pygame.display.flip()


class ProbeUI:
    def __init__(self, config: NdpConfig) -> None:
        self.config = config
        self.engine = ProbeEngine(config)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._force_refresh = threading.Event()
        self._screen = ScreenId.HOME
        self._state = ProbeState(interface=config.interface)
        self._redraw_now = threading.Event()
        self._discovery = DiscoveryUISession(config)
        self._buttons = PhysicalButtons(
            ButtonMapping(
                previous=config.ui_button_previous,
                select=config.ui_button_select,
                next=config.ui_button_next,
            ),
            debounce_seconds=config.ui_button_debounce_seconds,
        )
        self._web_thread: threading.Thread | None = None

    def get_state(self) -> ProbeState:
        with self._lock:
            return self._state

    def _engine_loop(self) -> None:
        while not self._stop.is_set():
            if self._force_refresh.is_set():
                self._force_refresh.clear()
            with self._lock:
                self._state = self.engine.refresh()
            time.sleep(self.engine.poll_interval())

    def _on_button(self, action: ButtonAction) -> None:
        if self._screen == ScreenId.DISCOVER:
            if action == ButtonAction.SELECT and self._discovery.on_select():
                self._redraw_now.set()
                return
            if action == ButtonAction.NEXT and self._discovery.on_next_skip():
                self._redraw_now.set()
                return
            if action == ButtonAction.PREVIOUS and self._discovery.running:
                self._discovery.cancel()
                self._redraw_now.set()
                return

        previous = self._screen
        if action == ButtonAction.PREVIOUS:
            self._screen = next_screen(self._screen, -1)
        elif action == ButtonAction.NEXT:
            self._screen = next_screen(self._screen, 1)
        elif action == ButtonAction.SELECT:
            self._force_refresh.set()

        if self._screen != previous:
            logger.info("UI screen -> %s", self._screen.name)

        self._redraw_now.set()

    def _run_startup(
        self,
        screen: pygame.Surface,
        raw_fb: RawFramebuffer | None,
        title_font: pygame.font.Font,
        body_font: pygame.font.Font,
        hint_font: pygame.font.Font,
    ) -> None:
        if not self.config.ui_splash_enabled and not self.config.ui_warmup_on_start:
            return

        warmup_done = threading.Event()
        warmup_error: list[str] = []

        def _warmup() -> None:
            try:
                if self.config.ui_warmup_on_start:
                    with self._lock:
                        self._state = self.engine.refresh()
                    for sid in ScreenId:
                        for line in lines_for_screen(sid, self._state):
                            body_font.render(line, True, COLOR_TEXT)
                warmup_done.set()
            except Exception as exc:  # pragma: no cover
                warmup_error.append(str(exc))
                warmup_done.set()

        worker = threading.Thread(target=_warmup, daemon=True, name="ndp-warmup")
        worker.start()

        splash_start = time.monotonic()
        status = "Caricamento..."
        while not self._stop.is_set():
            elapsed = time.monotonic() - splash_start
            if warmup_done.is_set():
                status = "Pronto" if not warmup_error else "Errore init"
            elif elapsed > 0.5:
                status = "Raccolta dati..."

            if self.config.ui_splash_enabled:
                draw_splash(
                    screen,
                    self.config,
                    title_font=title_font,
                    body_font=body_font,
                    version=__version__,
                    status_line=status,
                )
                _blit_frame(screen, raw_fb)

            ready = warmup_done.is_set() and elapsed >= self.config.ui_splash_min_seconds
            if ready:
                break
            time.sleep(0.05)

        if warmup_error:
            logger.warning("Warmup error: %s", warmup_error[0])

    def run(self) -> int:
        import pygame

        if self.config.web_enabled:
            from ndp.web.server import resolve_config_path, start_web_server

            config_path = self.config.source_path or resolve_config_path()
            self._web_thread = start_web_server(
                self.config,
                config_path,
                self.get_state,
            )

        if self.config.ui_backlight_enabled:
            enable_backlight(self.config.ui_backlight_gpio)

        screen, raw_fb = _init_display(self.config)

        title_font = _load_font(self.config.ui_font_size + 4)
        body_font = _load_font(self.config.ui_font_size)
        hint_font = _load_font(max(12, self.config.ui_font_size - 2))

        self._run_startup(screen, raw_fb, title_font, body_font, hint_font)

        worker = threading.Thread(target=self._engine_loop, daemon=True, name="ndp-engine")
        worker.start()

        poll_interval = 1.0 / max(10, self.config.ui_button_poll_hz)
        frame_interval = 1.0 / max(1, self.config.ui_fps)

        try:
            with self._buttons:
                last_frame = time.monotonic()

                while not self._stop.is_set():
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            self._stop.set()

                    self._buttons.poll(self._on_button)

                    now = time.monotonic()
                    if self._redraw_now.is_set() or (now - last_frame) >= frame_interval:
                        self._redraw_now.clear()

                        with self._lock:
                            state = self._state
                            current = self._screen

                        self._draw(screen, title_font, body_font, hint_font, current, state)
                        _blit_frame(screen, raw_fb)
                        last_frame = now

                    time.sleep(poll_interval)
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
        margin = self.config.ui_content_margin_side
        edge = self.config.ui_hint_edge
        text_gap = self.config.ui_content_text_gap
        text_width = content_width(self.config.ui_width, edge, margin)
        content_x = content_x_offset(edge, margin)
        text_x = content_text_x(edge, margin, text_gap)

        header = pygame.Rect(content_x, 0, text_width, 34)
        pygame.draw.rect(surface, COLOR_HEADER, header)

        title = title_font.render(screen_id.name, True, COLOR_ACCENT)
        surface.blit(title, (text_x, 6))

        dots = self._screen_dots(screen_id)
        dots_surface = hint_font.render(dots, True, COLOR_MUTED)
        surface.blit(
            dots_surface,
            (content_x + text_width - dots_surface.get_width() - 8, 10),
        )

        if screen_id == ScreenId.DISCOVER:
            body_lines = self._discovery.display_lines()
        else:
            body_lines = lines_for_screen(screen_id, state)

        y = 42
        line_step = self.config.ui_font_size + self.config.ui_line_spacing
        for line in body_lines:
            rendered = body_font.render(line, True, COLOR_TEXT)
            if rendered.get_width() > text_width - text_gap - 20:
                line = line[:28] + "…"
                rendered = body_font.render(line, True, COLOR_TEXT)
            surface.blit(rendered, (text_x, y))
            y += line_step

        draw_button_hints(
            surface,
            hint_font,
            edge=self.config.ui_hint_edge,
            width=self.config.ui_width,
            height=self.config.ui_height,
            color=COLOR_MUTED,
            margin=margin,
            y_offset=self.config.ui_hint_y_offset,
        )

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
